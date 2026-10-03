# Spec: 013 — Governed LLM Access and Telegram Admission

> **Backlog:** BL-23
> **Status:** 🔶 T2–T14 implementados localmente (diseño aprobado 2026-09-13);
> rollout Collector/Grafana, dashboards/alertas y validación Railway completa
> del cambio de modelo en caliente pendientes — ver `verification.md` y BL-23
> **Target:** convertir la entrada Telegram y el acceso a modelos LLM en
> capabilities gobernadas, idempotentes, configurables y observables.

---

## Requirement

AncoraMind usa Agno como runtime agentic, Telegram como canal y OpenRouter como
proveedor de inferencia. El provider y el modelo físicos se crean actualmente al
arrancar desde variables de entorno. El webhook, el loop de tools, las llamadas
LLM anidadas y la telemetría no comparten todavía una política transversal de
identidad, presupuesto, coste y correlación.

Un incidente observado hizo que un único «Hola» apareciera asociado a unas 78
inferencias. El código posterior reproduce y corrige un loop de Agno 2.9.0 ante
tool calls de OpenRouter malformadas, pero faltan los logs de producción para
atribuir forénsicamente las 78 llamadas a una única causa. Esta spec trata la
amplificación como riesgo sistémico aunque esa evidencia quede incompleta.

La identidad de una entrega Telegram y la ejecución resultante deben cumplir:

```text
same bot identity + same Telegram update_id
=> at most one Agent execution
=> at most one persisted logical response/action
```

Toda inferencia debe cumplir:

```text
LLM request
=> Governed LLM Access
=> ExecutionContext
=> RuntimeConfigSnapshot
=> ExecutionBudget
=> structured telemetry without personal content
```

### Must Have

#### Telegram admission and idempotency

- AncoraMind será propietario del endpoint de admission situado delante del
  runtime de Agno.
- Validar `X-Telegram-Bot-Api-Secret-Token` antes de cualquier persistencia o
  acceso personal.
- Rechazar chats que no sean privados y usuarios fuera de la allowlist antes de
  invocar el Agent.
- Persistir de forma durable `telegram_update_id` con una restricción única por
  identidad del bot.
- Registrar por separado cada delivery HTTP y su `X-Railway-Request-Id`.
- Una entrega duplicada devuelve `2xx` sin volver a ejecutar IA, tools, acciones
  ni respuestas.
- El `2xx` de un update nuevo solo se devuelve después de un commit durable que
  permita recuperar trabajo que todavía no haya llegado a `agent_started`.
- Aplicar semántica at-most-once estricta: un crash después de
  `agent_started` produce `failed_ambiguous` y no relanza automáticamente el
  Agent.
- Propuestas, acciones y respuestas lógicas tendrán idempotencia defensiva
  adicional.

#### Runtime model configuration

- Configuración dinámica tipada mediante Pydantic y almacenada como revisiones
  inmutables en PostgreSQL.
- Activación atómica mediante compare-and-swap y auditoría de actor, motivo,
  revisión anterior y checksum.
- `RuntimeConfigManager.snapshot()` debe leer únicamente memoria y no consultar
  PostgreSQL o disco en la ruta crítica.
- Mantener last-known-good si una revisión nueva es inválida.
- Mantener un bootstrap seguro en environment (`DEFAULT_MODEL` o ruta lógica
  equivalente) para cold start o recuperación.
- Cada run captura una revisión inmutable al comenzar; un cambio posterior solo
  afecta a nuevas ejecuciones.
- Las API keys, tokens y credenciales no forman parte de la configuración
  dinámica y permanecen en Railway secrets/environment.
- El control plane inicial será una API administrativa HTTPS protegida, operada
  mediante scripts HTTP; una CLI podrá añadirse después como cliente de la misma
  API.

#### Governed LLM access

- Ningún componente de producto creará o invocará providers físicos fuera de
  una abstracción `LLMAccess`.
- El Agent utilizará rutas lógicas versionadas como
  `ancoramind-default-r<N>`, `ancoramind-fast-r<N>` y
  `ancoramind-vision-r<N>`.
- LiteLLM Proxy es el target de Gateway y se desplegará como servicio privado en
  Railway con PostgreSQL dedicado.
- Si LiteLLM no está disponible, AncoraMind falla cerrado y no hace bypass
  directo al provider.
- OpenRouter permanece detrás de LiteLLM y conserva su fallback interno entre
  providers.
- El Agent completo y el modelo de Agno no se reintentan automáticamente.
- Toda inferencia anidada, incluida la extracción documental, comparte el mismo
  contexto, presupuesto, configuración y trace.

#### Execution budget and admission limits

- Runtime máximo por update: 120 segundos.
- Máximo de 6 llamadas lógicas al modelo por update.
- `tool_call_limit` target: 12 como hard safety ceiling, no como mecanismo
  principal de protección.
- Máximo de 8 requests al Gateway por update y 2 intentos por llamada lógica.
- Bloquear una segunda ejecución de la misma tool con los mismos argumentos
  después de un resultado exitoso.
- Una ejecución concurrente por chat y usuario; máximo global inicial de 2.
- Máximo de 5 updates en cola por chat y 20 pendientes globales.
- Rate limit inicial por usuario/chat: burst 5, 10 updates/minuto y 120/hora.
- Los duplicados no consumen rate limit.
- Un rechazo por rate/budget devuelve `2xx` a Telegram y no realiza inferencia.

#### Reliability, cost and circuit breaker

- Distinguir explícitamente retry, fallback y circuit breaker.
- Fase inicial: 0 retries de Agno, 0 retries de LiteLLM y 0 fallbacks
  cross-model de LiteLLM; fallback interno de OpenRouter habilitado.
- Los errores de autenticación, autorización, request inválido, modelo no
  encontrado y schema/payload inválido no son retryable.
- Timeout previo a tokens, errores de red, `429` y `5xx` solo podrán habilitar
  retry/fallback futuro bajo un límite agregado de intentos.
- El Gateway será propietario de cooldown/circuit; un circuito abierto no debe
  seguir llamando al upstream afectado.
- Registrar coste real cuando LiteLLM/OpenRouter lo exponga y estimado en caso
  contrario.
- Mantener el hard economic limit de OpenRouter como última barrera.

#### Telemetry and privacy

- OpenTelemetry es el estándar de observabilidad.
- AncoraMind y LiteLLM exportan mediante OTLP a un OpenTelemetry Collector
  upstream privado en Railway; Grafana Cloud es el backend inicial.
- La observabilidad es fail open: una caída del Collector o Grafana no bloquea
  Telegram, el Core ni el Gateway.
- La telemetría de producto de Agno se desactiva en Agent, AgentOS y environment.
- Correlacionar `railway_request_id`, `telegram_update_id`,
  `telegram_message_id`, `correlation_id`, `agno_run_id`, `agno_session_id`,
  `gateway_request_id` y `provider_request_id`.
- Registrar ruta lógica, provider/model, revisión de config, contadores,
  tokens, coste, latencia, retries, fallback, circuit y estado.
- No exportar prompts, mensajes Telegram, respuestas completas, documentos,
  extracciones ni argumentos/resultados completos de tools.
- PostgreSQL conserva la auditoría durable; Grafana no es fuente de verdad.

### Should Have

- PostgreSQL `LISTEN/NOTIFY` para invalidar la cache de configuración, más
  reconciliación lenta y recuperación tras pérdida de notificaciones.
- Benchmark p50/p95/p99 del overhead de LiteLLM frente a la latencia total del
  modelo, incluyendo TTFT.
- Dashboards y alertas para amplificación, coste, tools repetidas, fallback,
  circuit open, rate limits y `failed_ambiguous`.
- Alias versionados conservados durante una ventana de rollback.
- Diseño compatible con claims PostgreSQL y locks distribuidos si se escala en
  el futuro, aunque producción mantenga una réplica inicialmente.

### Won't Have (this spec)

- Kubernetes, service mesh o gateways enterprise.
- Sustitución de Agno como runtime agentic.
- UI administrativa o administración de config mediante Telegram/LLM tools.
- Replay automático del Agent después de `agent_started`.
- Garantía exactly-once para `Telegram.sendMessage`, que no ofrece idempotency
  key externa.
- Bypass directo a OpenRouter cuando LiteLLM esté activo y falle.
- Captura indiscriminada de contenido para debugging/tracing.
- Fallback cross-model LiteLLM en la primera activación.
- Escalado horizontal inicial.

---

## Success Criteria

1. Veinte deliveries concurrentes del mismo `update_id` producen una fila de
   interacción y una única ejecución Agent/LLM.
2. Railway request IDs distintos para el mismo update quedan registrados como
   deliveries duplicadas de una misma `correlation_id`.
3. Un cambio de modelo/ruta afecta al siguiente run sin redeploy y no modifica
   un run ya iniciado.
4. Una revisión inválida conserva last-known-good o el bootstrap seguro.
5. Ningún run supera sus límites de runtime, model calls, Gateway requests,
   tools o repetición de argumentos.
6. La tool call número 12 puede ejecutarse si queda budget; la 13 se rechaza.
7. Un primary fallido no multiplica requests por encima del attempt budget.
8. Con circuit abierto no se llama al upstream afectado.
9. Rate o budget agotados impiden nuevas inferencias.
10. Un crash antes de `agent_started` es recuperable; después queda
    `failed_ambiguous` sin replay del Agent.
11. Grupos y usuarios no allowlisted no alcanzan Agno.
12. La extracción documental usa la misma config, budget, correlación y
    contabilidad que el Agent principal.
13. Una caída de LiteLLM falla cerrada sin bypass; una caída del Collector falla
    abierta respecto a la funcionalidad.
14. Una interacción se reconstruye de Telegram a provider mediante
    `correlation_id` sin consultar contenido personal.
15. Tests de privacidad demuestran que logs/traces no contienen prompts,
    respuestas, documentos, extracciones ni argumentos/resultados completos.
16. Unit tests, integration tests, Ruff y los checks de migración del alcance
    pasan antes del cierre.
