# Tasks: 013 — Governed LLM Access and Telegram Admission

> Las tareas permanecen abiertas hasta su implementación y verificación. Cada
> incremento debe poder desplegarse de forma segura o quedar detrás de feature
> flags. No marcar tareas como completadas por el mero hecho de crear esta spec.

## T1: Artefactos, baseline y rollout

- [x] Crear `spec.md`, `design.md`, `tasks.md` y plantilla de `verification.md`.
- [x] Crear ADR-004, ADR-005 y ADR-006.
- [x] Registrar BL-23 y actualizar architecture/governance/AGENTS/README.
- [ ] Capturar baseline automatizado del flujo actual: códigos HTTP, número de
      model calls, tool calls, tokens y latencias.
- [ ] Documentar qué evidencia del incidente de ~78 inferencias sigue ausente.
- [ ] Definir feature flags de rollout para admission, processor, runtime config,
      `LLMAccess`, LiteLLM y OpenTelemetry.

## T2: Estrategia de migraciones

- [x] Resolver BL-12 introduciendo Alembic o una estrategia equivalente
      explícitamente aprobada antes de modificar producción.
- [x] Crear migraciones aditivas para las tablas de specs/013 y las extensiones
      de `action_proposals`.
- [x] Mantener `migrations/init.sql` como baseline fresh idempotente si sigue
      aportando valor operacional.
- [x] Probar upgrade sobre una BD con datos existentes.
- [x] Probar instalación desde cero.
- [x] Probar downgrade de la última migración sin pérdida no documentada.
- [x] Actualizar `tests/integration/conftest.py` para limpiar las nuevas tablas.

**Gate:** no desplegar el ledger contra producción sin una ruta de migración
reproducible y validada.

## T3: Interaction ledger

- [x] Crear modelos de interacción, delivery y estados terminales.
- [x] Implementar repositorio async con `sqlalchemy.text()` parametrizado.
- [x] Añadir `UNIQUE(bot_id, telegram_update_id)` y claim atómico.
- [x] Registrar `railway_request_id`, `telegram_message_id` y `correlation_id`.
- [x] Normalizar y cifrar el payload recuperable; mantener claves solo en
      Railway secrets.
- [x] Implementar retención y eliminación del payload según estado.
- [x] Añadir tests unitarios e integración de concurrencia y duplicados.

**Acceptance:** B y V implementadas en ledger/admission. A queda parcial hasta
que T5 conecte el claim con una única ejecución real del Agent.

## T4: Telegram admission endpoint

- [x] Crear endpoint `/telegram/webhook` propiedad de AncoraMind delante de
      Agno, conservando la URL pública existente.
- [x] Validar `X-Telegram-Bot-Api-Secret-Token`.
- [x] Aplicar private-chat enforcement real.
- [x] Aplicar `ALLOWED_TELEGRAM_USER_IDS` como allowlist real.
- [x] Implementar rate limit burst/minuto/hora y capacidad de cola.
- [x] Devolver `2xx` solo después del commit durable.
- [x] Reconocer duplicados/rechazos con `2xx` sin IA.
- [x] Devolver `500/503` si no puede persistirse un update nuevo.
- [x] Añadir tests de seguridad para grupos, canales y usuarios no autorizados.

**Acceptance:** N, O, V y W implementados en admission HTTP. La ejecución del
Agent sigue pendiente de T5; el feature flag permanece desactivado por defecto.

## T5: Processor, state machine and response outbox

- [x] Implementar la máquina de estados de interacción.
- [x] Crear worker in-process con claim atómico de `accepted`.
- [x] Ordenar procesamiento por chat.
- [x] Aplicar locks por chat/usuario y semáforo global.
- [x] Crear `logical_responses` y delivery tracking por chunk.
- [x] Persistir respuesta lógica antes de enviar a Telegram.
- [x] Desactivar inicialmente el streaming visible en Telegram y refrescar
      `typing` durante runs largos.
- [x] Implementar recuperación de `accepted`/`response_ready` y transición de
      estados ambiguos sin replay.
- [x] Añadir crash-injection tests en cada frontera crítica.

**Acceptance:** J, K, L y M implementados en processor/outbox. El processor y
admission continúan detrás de flags `false` por defecto; T7 reemplazará el
adaptador temporal Agno por `LLMAccess` y Agent per-run.

## T6: RuntimeConfigManager and admin API

- [x] Definir schemas Pydantic con `extra="forbid"` e invariantes cross-field.
- [x] Implementar revisiones inmutables, active pointer y activations append-only.
- [x] Implementar bootstrap desde environment y last-known-good.
- [x] Implementar `snapshot()` sin I/O y snapshots inmutables por run.
- [x] Implementar activación compare-and-swap y rollback.
- [x] Crear API administrativa protegida: status, validate, create revision,
      activate y rollback.
- [x] Crear scripts `curl`/PowerShell sin exposición de secretos.
- [ ] Añadir `LISTEN/NOTIFY`, reconexión y reconciliación lenta en un incremento
      posterior al funcionamiento con una réplica.
- [x] Añadir tests de activación concurrente, revisión inválida y notificación
      perdida.

**Acceptance:** C, D, T y U.

## T7: Governed LLM Access and per-run Agent factory

- [x] Introducir `LLMAccess` como única frontera de inferencia de runs gobernados.
- [x] Implementar `ExecutionContext` y propagación mediante `ContextVar`.
- [x] Crear Agent por run con ID lógico estable, `run_id` explícito y config
      snapshot fija.
- [x] Implementar `GovernedModel`/adaptador que exija contexto y falle cerrado.
- [x] Propagar `traceparent`, `correlation_id`, `llm_call_id` y revisión.
- [x] Registrar usage, request IDs, latencia y error class.
- [x] Mantener temporalmente OpenRouter directo solo detrás de `LLMAccess`.
- [x] Cambiar el default de `AGENT_TOOL_CALL_LIMIT` y el fallback del factory a
      12; actualizar tests y documentación operativa en ese incremento.
- [x] Configurar retries de Agent y Model explícitamente a 0.

**Acceptance:** Q parcial, X e Y parcialmente implementados en el processor
T5+T7. El webhook legado AgentOS y la extracción documental directa quedaban
como excepciones transitorias (la extracción se resolvió en T9; el webhook
permanece hasta el rollout T4/T5); LiteLLM fail-closed pertenece a T11.

## T8: Execution budget

- [x] Implementar deadline total de 120 segundos.
- [x] Limitar a 6 model calls lógicas y 8 Gateway requests por update.
- [x] Limitar a 2 intentos Gateway por llamada lógica.
- [x] Integrar tool hooks de Agno y el hard ceiling de 12.
- [x] Calcular fingerprints HMAC de tool + argumentos canónicos.
- [x] Bloquear repetición posterior a éxito y acotar retries tras error.
- [x] Hacer los contadores seguros frente a tools async concurrentes.
- [x] Implementar estimación/reserva/reconciliación de coste.
- [x] Detener el run de forma controlada con estado y telemetry explícitos.

**Acceptance:** G y H implementados en runs gobernados. El Gateway no tiene
retries/fallbacks activos hasta T11/T12, pero el budget ya reserva y valida el
límite agregado y los 2 attempts por llamada lógica para esa evolución.

## T9: Document extraction port

- [x] Definir `DocumentExtractionPort` fuera de Agno.
- [x] Eliminar la creación directa de `agno.agent.Agent` en el dominio.
- [x] Implementar un adaptador de extracción mediante `LLMAccess`.
- [x] Compartir config, deadline, contadores, coste y trace del run principal.
- [x] Registrar provider/model reales en `ai_extractions`.
- [x] Sustituir el `except Exception: pass` por resultado controlado y metadata
      observable sin exponer contenido.

**Acceptance:** P implementado en runs gobernados. El path AgentOS legado usa
un contexto bootstrap standalone gobernado (misma frontera `LLMAccess`, budget
propio) sin filas de `llm_usage_events` porque no existe interacción que
referenciar; su retiro llega con el rollout T4/T5.

## T10: OpenTelemetry and privacy

- [x] Desactivar telemetría de producto con `Agent(telemetry=False)`,
      `AgentOS(telemetry=False)` y `AGNO_TELEMETRY=false`.
- [x] Añadir logs JSON estructurados con `correlation_id`.
- [x] Instrumentar admission, queue, Agent, LLM, tools, budget y delivery.
- [x] Exponer métricas agregadas de volumen, latencia, tokens, coste, errores y
      budget. Retries/fallbacks/rate limits/circuit se instrumentarán al
      introducir sus mecanismos efectivos en T11/T12.
- [x] Versionar configuración del OpenTelemetry Collector upstream privado Railway.
- [x] Configurar allowlist/redaction, memory limiter, batch y cola/retry acotados.
- [x] Implementar exporter OTLP opcional al Collector y validar el manifiesto
      localmente con la imagen fijada.
- [ ] Desplegar Collector privado en Railway y confirmar exportación real a
      Grafana Cloud (requiere secretos y rollout explícito).
- [x] Propagar W3C `traceparent` hacia el Gateway/provider transitorio.
- [x] Crear tests que fallen si logs/traces contienen contenido sensible.
- [ ] Crear dashboards y alertas iniciales (requiere instancia Grafana Cloud real).

**Acceptance:** I, R y S implementados localmente. El provisionamiento/despliegue
real del servicio Collector privado (checklist pendiente arriba) y
dashboards/alertas de Grafana requieren un rollout Railway explícito y no se
ejecutan desde el repositorio.

## T11: LiteLLM Proxy pilot

- [ ] Provisionar PostgreSQL Railway dedicado para LiteLLM (rollout pendiente:
      requiere aprobación de coste y creación real del servicio).
- [ ] Desplegar LiteLLM como servicio privado en Railway. La imagen/version
      digest ya está fijada (`gateway/Dockerfile`,
      `ghcr.io/berriai/litellm@sha256:a3715fa7…c62bf`) y validada localmente.
- [x] Desactivar Swagger, Redoc y OpenAPI (`NO_DOCS`/`NO_REDOC`/`NO_OPENAPI`;
      verificado localmente: `/docs`, `/redoc` y `/openapi.json` devuelven 404).
- [x] Crear virtual key exclusiva para AncoraMind/environment
      (`scripts/litellm_create_virtual_key.py`, restringida a los tres aliases;
      enforcement verificado: key inválida ⇒ 401 del propio Gateway).
- [x] Mantener provider keys y master key fuera del repositorio: el config usa
      exclusivamente `os.environ/...`; los secretos viven en Railway/local env.
- [x] Crear aliases lógicos versionados (`gateway/litellm-config.yaml` expone
      `ancoramind-default-r1`, `ancoramind-fast-r1`, `ancoramind-vision-r1`).
- [x] Configurar OpenRouter como upstream (modelos `openrouter/...`); el
      fallback interno entre providers lo conserva OpenRouter
      (`openrouter_provider_fallback` del runtime config).
- [x] Mantener inicialmente retries y cross-model fallback de LiteLLM a 0
      (`router_settings.num_retries: 0`; el smoke confirmó
      `Available Model Group Fallbacks=None`).
- [x] Verificar fail closed y ausencia de bypass: `LITELLM_PROXY_ENABLED=true`
      exige URL privada + virtual key (Settings fail-closed); `LLMAccess` y el
      AgentOS legado componen únicamente `OpenAILike` hacia el Gateway con el
      alias del snapshot. Smoke local con OpenRouter dummy ⇒ 401 del upstream
      sin fallback.
- [ ] Ejecutar benchmark p50/p95/p99 y TTFT frente a OpenRouter directo
      (requiere una OPENROUTER_API_KEY real y el rollout Railway).
- [ ] Revisar advisories y superficies de administración antes de producción
      (documentación ya desactivada; revisión de superficie en el rollout).

**Acceptance:** Q implementado localmente (fail closed sin bypass verificado
con el Gateway real). El despliegue Railway privado, el benchmark con clave
real y la revisión de superficie productiva requieren un rollout explícito.

## T12: Reliability and cost governance

- [x] Configurar cooldown/circuit y probar `CLOSED/OPEN/HALF_OPEN`
      (`router_settings.allowed_fails: 3` + `cooldown_time: 60` en
      `gateway/litellm-config.yaml`, igual a `gateway.cooldown_seconds` del
      runtime config). Validado localmente con un deployment de upstream muerto:
      3 fallos consecutivos abrieron el circuit, las siguientes llamadas
      fast-failaron con `No deployments available` (429) **sin ninguna llamada
      al upstream**, y tras el cooldown la siguiente petición probó el upstream
      de nuevo (HALF_OPEN → CLOSED).
- [x] Aplicar RPM, TPM y max parallel requests por virtual key/ruta
      (`model_info.rpm/tpm` por alias + `rpm_limit`/`tpm_limit`/
      `max_parallel_requests` en `scripts/litellm_create_virtual_key.py`).
      Enforcement verificado localmente: key con `rpm_limit=2` ⇒ 429
      fast-fail (<50 ms) sin tocar el upstream.
- [x] Persistir spend logs y coste real/estimado sin contenido:
      `ancora.llm_usage_events` ya persiste coste estimado/real por llamada;
      `LlmUsageRepository.summarize_spend` lo agrega por día/mes/ruta
      (coste real con precedencia sobre el estimado, sin contenido).
- [x] Configurar budgets por route, día y mes (`CostGovernanceConfig` en el
      runtime config: `daily_budget_usd`, `monthly_budget_usd`,
      `route_monthly_budgets_usd`; invariante: rutas de pago exigen pricing +
      cost governance + coste máximo por interacción).
- [x] Alertar al 60%/80% y hacer hard stop al 90% del límite externo
      (`evaluate_cost_governance` al inicio de cada run: contadores
      metadata-only `ancora.cost_governance.alert`; hard stop ⇒
      `CostGovernanceError` → `failed_controlled` sin replay, sin inferencia).
- [x] Mantener el hard limit de OpenRouter al 100%: el hard stop de AncoraMind
      al 90% preserva el margen restante para que el límite externo nunca se
      alcance; opcionalmente la virtual key lleva `max_budget`+
      `budget_duration` como backstop en el propio Gateway. OpenRouter expone
      `GET /api/v1/key` (`limit`/`limit_remaining`/usage diario/semanal/mensual)
      para reconciliar el límite externo en el rollout.
- [x] Verificar qué intentos internos expone OpenRouter para evitar falsa
      contabilidad (investigado y documentado en verification.md: el response
      incluye `usage.cost`/`cost_details` del intento servido, un objeto de
      routing con `attempt` y el endpoint seleccionado, y `usage` refleja sólo
      el intento final; la verificación con clave real queda pendiente del
      rollout).
- [x] Evaluar un único retry o fallback cross-model futuro solo con datos y
      sin superar el attempt budget — **decisión: mantener 0 por ahora**.
      Requiere antes el benchmark T11 con clave real y datos de fallos
      reales; el attempt budget ya reserva 2 attempts por llamada lógica para
      esa evolución sin amplificar el volumen.

**Acceptance:** E y F verificados localmente (attempt budget intacto con
retries a 0; circuit open ⇒ cero llamadas al upstream). El benchmark con
clave real y la reconciliación de coste real con OpenRouter quedan pendientes
del rollout Railway.

## T13: Hardening, runbooks and closure

> T13 opera bajo una restricción explícita de alcance: todo el hardening que
> requiera recursos externos (Railway, Grafana Cloud, Telegram real, OpenRouter
> con clave real) se deja como checklist pendiente del rollout. T13 solo
> entrega hardening verificable localmente (carga/crash/retención/runbooks) y
> marca como pendientes E2E Railway, rotación real de secretos, dashboards y
> `verification.md` con evidencia real. BL-23 no se cierra en T13: queda en
> estado "implementado localmente, E2E pendiente".

- [x] Ejecutar load tests y duplicados concurrentes (local, sin costes externos).
      `tests/integration/test_hardening_013.py`: 20 duplicados → 1
      interaction/20 deliveries/1 claim; burst de 5 updates → 5 runs
      ordenados, exactamente-once.
- [x] Ejecutar crash injection y reinicios/deploys durante cada estado (local).
      Misma suite: `agent_started` → `failed_ambiguous` sin replay ni delivery;
      `delivery_started` → `failed_ambiguous` sin reenvío; `response_ready` →
      delivery sin rerun del Agent.
- [x] Validar retención/borrado con el cifrado/purga implementados (local).
      Misma suite: `failed_ambiguous` + 8 días → ciphertext/version
      borrados, fingerprint y metadata conservados.
- [x] Crear runbooks de Gateway down, circuit open, budget exhausted,
      `failed_ambiguous`, Collector down y rollback de config.
      Entregado `docs/runbooks-013.md` (§0–§7 + §8 pendientes de rollout).
- [x] Ejecutar unit tests, integration tests, Ruff y checks de migración.
      Gates finales T13 abajo (352 unit + 59 integration, Ruff, mypy T13,
      Alembic head 0003, Docker build/smoke).
- [x] Completar `verification.md` con evidencia local y marcar el resto ⏳.
      Header T2–T13, filas de hardening T13 y sección T13 añadidas; E2E,
      rotación real, Grafana y benchmark quedan ⏳ explícitos.
- [x] Actualizar BACKLOG, AGENTS, README y deployment docs al estado implementado.
      (AGENTS/ BACKLOG/ README/ deployment-railway/ development/ runbooks-013
      actualizados en T13; ver resumen final.)
- [x] Dejar E2E Telegram en Railway, rotación real, acceso Grafana y benchmark
      con clave real como pendientes explícitos del rollout (no cierran BL-23).
       Checklist en `docs/runbooks-013.md` §9 y `verification.md`.
- [ ] Cerrar BL-23 solo cuando la matriz A–Y esté verificada (pendiente:
      E2E Railway + evidencia real).

### Entregables T13 (añadidos en esta tarea)

| Entregable | Fichero |
|---|---|
| Runbooks operativos (Gateway down, circuit open, budget, ambiguous, Collector, rollback) | `docs/runbooks-013.md` |
| Checklist de rollout Railway/Grafana/Telegram pendiente | `docs/runbooks-013.md` §9 + `specs/013/verification.md` |
| Tests de carga/crash/retención verificables localmente | `tests/integration/test_hardening_013.py` (extendido en T13) |

## T14: Cambio de modelo en caliente — publicación aditiva de aliases

> Cierra el hueco detectado el 2026-09-18: la decisión 9 de ADR-005
> ("publicación del alias Gateway") y `design.md` §11 describían una publicación
> en dos fases que nunca se implementó, por lo que un cambio de modelo físico
> seguía exigiendo editar `gateway/litellm-config.yaml` y redesplegar LiteLLM.
> Enmienda de gobernanza: `docs/adr/ADR-005-…md` §Enmienda (decisiones 15–18).

Las fases se registran con su estado para poder auditar el avance:

| Fase | Alcance | Estado |
|---|---|---|
| 1 | Gobernanza: enmienda ADR-005 (fuente de verdad aditiva, publicación por operador, `/model/*` only) | ✅ |
| 2 | Gateway: `store_model_in_db: true` + validación local del arranque y aliases | ✅ |
| 3 | Script `scripts/litellm_gateway_alias.py` (publish/grant/verify/retire) + allowlist extensible de la virtual key | ✅ |
| 4 | Tests unitarios y Ruff en el gate global | ✅ |
| 5 | Documentación: runbooks §2.1/§2.2, deployment-railway, development, `.env.example`, AGENTS, BACKLOG | ✅ |
| 6 | Rollout Railway: publicar `r2`, activar revisión y demostrar el cambio sin reinicio | ✅ (2026-09-19) |

- [x] **Fase 1 — Enmienda de gobernanza.** `ADR-005` registra el motivo (decisión
  9 no implementada + mutación en sitio de `r1` el 2026-09-18), y fija: aliases
  base inmutables en Git, DB sólo aditiva, publicación por script de operador
  (AncoraMind nunca tiene la master key) y prohibición de escribir settings por
  API/UI por el overlay de `LiteLLM_Config`.
- [x] **Fase 2 — Habilitar la vía runtime.** `store_model_in_db: true` en
  `general_settings`; validado levantando `gateway/docker-compose.litellm.yml`
  (readiness 200 y tres aliases base publicados).
- [x] **Fase 3 — Script de operador.** `scripts/litellm_gateway_alias.py` con
  `publish` (idempotente, `--dry-run`, guard de alias base), `grant` (aditivo),
  `verify` (distingue aliases de Git y de runtime) y `retire` (guard de alias
  base). `scripts/litellm_create_virtual_key.py` acepta
  `LITELLM_VIRTUAL_KEY_ALIASES` para autorizar generaciones nuevas.
- [x] **Fase 4 — Tests y lint.** `tests/unit/test_gateway_alias_script.py` y
  nuevas aserciones en `tests/unit/test_gateway_config.py` (publicación aditiva
  habilitada, inmutabilidad de los aliases base, allowlist de la key). Se
  endurecen además los dos tests de LiteLLM en `tests/unit/test_config.py`
  (`monkeypatch.delenv` + `_env_file=None`) para que un entorno con
  `LITELLM_PROXY_*` exportadas no provoque un fallo espurio del gate.
- [x] **Fase 5 — Documentación.** `docs/runbooks-013.md` §2.1 (configuración
  efectiva) y §2.2 (procedimiento de dos fases con rollback),
  `docs/deployment-railway.md` §3.2 (caminos GitHub vs imagen + variable,
  corrección del `COPY`/root directory, paso de cambio de modelo),
  `docs/development.md`, `.env.example`, `AGENTS.md` y `BACKLOG.md`.
- [x] **Fase 6 — Rollout Railway.** Publicar `ancoramind-default-r2`, otorgarlo a
  la virtual key, activar la revisión runtime y confirmar el cambio de modelo sin
  reiniciar ningún servicio, incluyendo el ensayo de rollback. Ejecutado el
  2026-09-19 — evidencia completa en "Fase 6 — evidencia de rollout Railway"
  (infraoperación: `STORE_MODEL_IN_DB` estaba a `False` en Railway y se corrigió
  a `true` antes de publicar).

### Fase 6 — estado de preparación (2026-09-18)

**Modelo alternativo elegido:** `z-ai/glm-5.3-flash` ("Z.ai: GLM 5.3 Flash").
En el Gateway el valor es `openrouter/z-ai/glm-5.3-flash`. Verificado contra la
API de OpenRouter el 2026-09-18: modelo activo, multimodal
(text+image+video→text), contexto 1 048 576 tokens, y `tools`/`tool_choice` +
`structured_outputs`/`response_format` en los endpoints declarados (cubre las
capabilities `text`/`tool_calling`/`structured_output` de la ruta). Precio de
referencia del endpoint oficial Z.AI: 0.15 USD/M entrada y 0.50 USD/M salida
(los proveedores alternativos de OpenRouter van de 0.075 a 0.45 USD/M de
entrada); OpenRouter enruta dinámicamente entre ellos.

**Revisión candidata preparada:** `configs/ancoramind-default-r2.json`, derivada
de la revisión activa 1 cambiando sólo
`routing.routes.ancoramind-default.effective_gateway_route` a
`ancoramind-default-r2`. Checksum `ff9dbfb7bb7bfd1169f40f6191fe927041767c824180c
8bb042493faabd7ad33`, validada `valid` contra el esquema real.

Como `z-ai/glm-5.3-flash` es una **ruta de pago**, el invariante de T12 obliga a
incluir `pricing` + `cost_governance` + `max_estimated_cost_usd`. Techos
propuestos (ajustables antes de activar): límite externo 20 USD (igual que el
backstop OpenRouter), presupuesto diario 1 USD, mensual 20 USD, techo mensual de
la ruta `ancoramind-default` 10 USD, coste máximo por interacción 0.10 USD y
umbrales 60/80/90%. La estimación usa el precio oficial Z.AI; la comparación con
el coste real queda para la reconciliación de costes del rollout.

Justificación del techo por interacción: la estimación (T7/T12) reserva siempre
`max_output_tokens` completos por llamada (1024 × 0.50 USD/M = 0.000512 USD) más
la entrada aproximada por recuento de caracteres, de modo que una interacción al
peor caso dentro del budget vigente (6 model calls) ronda 0.005–0.006 USD.
0.10 USD deja ~18x de margen y no es el verdadero tope de gasto: los techos de
día/mes/ruta (que se evalúan con coste real, no estimado) y el límite externo de
OpenRouter son los que cortan el gasto; el techo por interacción es la segunda
línea contra bucles desbocados y picos de precio por llamada.

**Estado de la infraestructura Railway verificado el 2026-09-18:**

| Comprobación | Resultado |
|---|---|
| `STORE_MODEL_IN_DB` en el servicio LiteLLM | Existía como variable pero con valor **`False`** — la env var tiene precedencia sobre `general_settings.store_model_in_db` del yaml (el repo lo tenía a `true`). Corregido a `true` el 2026-09-19 antes de publicar (redeploy del Gateway) |
| Dominio público del Gateway | Ninguno — privado por diseño (ADR-005) |
| `RUNTIME_CONFIG_ADMIN_ENABLED`/`_TOKEN` en `ancoramind-app` | Ausentes ⇒ la API admin runtime config está **desactivada** en producción |
| CLI de Railway en la máquina local | No instalada |

Consecuencia operativa: los pasos que mutan el Gateway (`publish`, `grant`) y el
paso que activa la revisión exigen secretos que sólo están en Railway
(`LITELLM_MASTER_KEY`, `LITELLM_PROXY_VIRTUAL_KEY`) y no son recuperables por
esta sesión; y la activación requiere habilitar antes la API admin (lo que
impone generar `RUNTIME_CONFIG_ADMIN_TOKEN` y redeplegar la app: el arranque
falla cerrado si se activa `ENABLED` sin token). La secuencia exacta queda
preparada en `docs/runbooks-013.md` §2.2.

### Hueco conocido que permanece abierto

La decisión 9 de ADR-005 menciona también el **healthcheck del alias antes de la
activación**. T14 no lo impone en servidor: `RuntimeConfigManager.activate()`
sigue pudiendo activar una revisión que apunte a un alias inexistente, y el fallo
aparecería en la primera inferencia. La mitigación actual es procedimental —el
operador ejecuta `scripts/litellm_gateway_alias.py verify --alias <nuevo>` antes
de activar— pero no está garantizada por el código. Cerrarlo requiere que la
activación consulte el Gateway (o que el control plane reciba la lista de
aliases publicados) y debe evaluarse junto con la superficie de privilegio, ya
que hoy AncoraMind sólo posee la virtual key y no la master key.

### Evidencia local (2026-09-18)

Gateway LiteLLM `v1.100.1` vía `gateway/docker-compose.litellm.yml`, con
`store_model_in_db: true`:

| Comprobación | Resultado |
|---|---|
| `/health/readiness` tras el arranque | `200` |
| Aliases base tras el arranque | `ancoramind-default-r1`, `ancoramind-fast-r1`, `ancoramind-vision-r1` |
| Publicar `ancoramind-default-r2` con el Gateway en marcha | `Published … -> openrouter/gpt-5.6-luna` |
| `r2` en `/model/info` **sin reiniciar** | `runtime_published_aliases: ["ancoramind-default-r2"]` |
| Inferencia al alias recién publicado sin reinicio | `HTTP 401` con `Received Model Group=ancoramind-default-r2` (error de upstream por clave dummy, **no** `model not found`) |
| Segunda publicación de `r2` | `already published; nothing to do` (idempotente) |
| `grant` | `…-r1, …-fast-r1, …-vision-r1, …-default-r2` (aditivo, conserva la base) |
| `retire ancoramind-default-r2` | `1 deployment(s) removed`; la base `r1` intacta |
| Guard de alias base (`publish`/`retire` sobre `*-r1`) | Rechazado con exit code 1 |

Gates: `pytest tests/unit/` → **369 passed**; `ruff check src/ tests/ scripts/
migrations/` → **All checks passed**. Los tests de configuración se repiten con
`LITELLM_PROXY_ENABLED`/`_BASE_URL`/`_VIRTUAL_KEY`/`_DEFAULT_ROUTE` exportadas
para confirmar que el gate no depende del entorno local.

### Fase 6 — evidencia de rollout Railway (2026-09-19)

**Corrección previa obligatoria:** en Railway la variable `STORE_MODEL_IN_DB`
estaba a `False` (la env var tiene precedencia sobre el yaml del repo, que sí
decía `true`). Se corrigió a `true` + redeploy del Gateway antes de publicar.

**Infraoperación (sin secretos fuera de Railway):** acceso vía `railway ssh`
autenticado con un token de API de workspace revocable y una clave SSH
desechable (registrada y eliminada al terminar); los comandos se ejecutaron
dentro de los contenedores con scripts Python canalizados por stdin; la master
key, la virtual key y el admin token se leyeron y usaron únicamente desde las
variables de entorno de sus contenedores. El `grant` se hizo sin que la virtual
key transitara: se leyó vía prisma desde la propia BD del Gateway y se pasó a
`/key/update` con la master key, todo dentro del contenedor LiteLLM.

| Comprobación | Resultado |
|---|---|
| `/model/info` antes | 3 aliases r1 cargados de config, `db_model: False` |
| `POST /model/new` → `ancoramind-default-r2` | `200`; `model_id ad121da2…`; `db_model: True`; `openrouter/z-ai/glm-5.3-flash`; rpm 60 / tpm 250 000 (clonados de r1); parámetros cifrados con salt; **sin reiniciar el Gateway** |
| `grant` (`/key/update` aditivo) | `200`; allowlist = 3×r1 + `ancoramind-default-r2` |
| Smoke del alias (contenedor de la app, vía VK) | `200`; `model=ancoramind-default-r2`; coste 0.000008 USD. Nota: GLM es de razonamiento — con `max_tokens=10` el content sale vacío (todo el presupuesto se fue en reasoning) |
| Admin API (`_TOKEN` + `_ENABLED=true`) | Un deploy `CRASHED` (fail-closed correcto: el token se añadió después del snapshot de variables del deploy) → redeploy automático `SUCCESS` |
| `validate` de la candidata | `valid`; checksum canónico **`0e40ba0c24ae…668a6e21`** (difiere de los checksums locales de preparación por canonicalización; el canónico es el del servicio) |
| `create-revision` | `201`; revisión **2**; actor `jesus-r2-rollout`; razón "fase 6 T14: switch default route to glm-5.3-flash (r2)" |
| `activate` (CAS `expected_current_revision: 1`) | `200`; `active_revision: 2` |
| Mensaje real de Telegram | Bot responde; logs de OpenRouter confirman `z-ai/glm-5.3-flash` |
| `llm_usage_events` | `config_revision=2`, `effective_gateway_route='ancoramind-default-r2'`, `estimated_cost=0.00094790`, `cost_source='pricing_snapshot'`, `completed`, sin retries ni fallback |
| Ensayo de rollback | `POST /rollback` → revisión 1 (checksum `73617adb…`); mensaje real → Luna confirmado en OpenRouter y BD (`config_revision=1`, `route=…-r1`); reactivación → revisión 2 (**estado final**) |

Estado final: revisión 2 activa; Gateway con 3 aliases r1 (config) + `r2`
(BD, `db_model`); ningún servicio reiniciado por el cambio de modelo (el único
redeploy de la app fue el de habilitar la API admin, y el del Gateway el de
corregir `STORE_MODEL_IN_DB`, ambos ajenos a la publicación del alias).

