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

- [ ] Resolver BL-12 introduciendo Alembic o una estrategia equivalente
      explícitamente aprobada antes de modificar producción.
- [ ] Crear migraciones aditivas para las tablas de specs/013 y las extensiones
      de `action_proposals`.
- [ ] Mantener `migrations/init.sql` como baseline fresh idempotente si sigue
      aportando valor operacional.
- [ ] Probar upgrade sobre una BD con datos existentes.
- [ ] Probar instalación desde cero.
- [ ] Probar downgrade de la última migración sin pérdida no documentada.
- [ ] Actualizar `tests/integration/conftest.py` para limpiar las nuevas tablas.

**Gate:** no desplegar el ledger contra producción sin una ruta de migración
reproducible y validada.

## T3: Interaction ledger

- [ ] Crear modelos de interacción, delivery y estados terminales.
- [ ] Implementar repositorio async con `sqlalchemy.text()` parametrizado.
- [ ] Añadir `UNIQUE(bot_id, telegram_update_id)` y claim atómico.
- [ ] Registrar `railway_request_id`, `telegram_message_id` y `correlation_id`.
- [ ] Normalizar y cifrar el payload recuperable; mantener claves solo en
      Railway secrets.
- [ ] Implementar retención y eliminación del payload según estado.
- [ ] Añadir tests unitarios e integración de concurrencia y duplicados.

**Acceptance:** A, B y V.

## T4: Telegram admission endpoint

- [ ] Crear endpoint `/telegram/webhook` propiedad de AncoraMind delante de
      Agno, conservando la URL pública existente.
- [ ] Validar `X-Telegram-Bot-Api-Secret-Token`.
- [ ] Aplicar private-chat enforcement real.
- [ ] Aplicar `ALLOWED_TELEGRAM_USER_IDS` como allowlist real.
- [ ] Implementar rate limit burst/minuto/hora y capacidad de cola.
- [ ] Devolver `2xx` solo después del commit durable.
- [ ] Reconocer duplicados/rechazos con `2xx` sin IA.
- [ ] Devolver `500/503` si no puede persistirse un update nuevo.
- [ ] Añadir tests de seguridad para grupos, canales y usuarios no autorizados.

**Acceptance:** N, O y W.

## T5: Processor, state machine and response outbox

- [ ] Implementar la máquina de estados de interacción.
- [ ] Crear worker in-process con claim atómico de `accepted`.
- [ ] Ordenar procesamiento por chat.
- [ ] Aplicar locks por chat/usuario y semáforo global.
- [ ] Crear `logical_responses` y delivery tracking por chunk.
- [ ] Persistir respuesta lógica antes de enviar a Telegram.
- [ ] Desactivar inicialmente el streaming visible en Telegram y refrescar
      `typing` durante runs largos.
- [ ] Implementar recuperación de `accepted`/`response_ready` y transición de
      estados ambiguos sin replay.
- [ ] Añadir crash-injection tests en cada frontera crítica.

**Acceptance:** J, K, L y M.

## T6: RuntimeConfigManager and admin API

- [ ] Definir schemas Pydantic con `extra="forbid"` e invariantes cross-field.
- [ ] Implementar revisiones inmutables, active pointer y activations append-only.
- [ ] Implementar bootstrap desde environment y last-known-good.
- [ ] Implementar `snapshot()` sin I/O y snapshots inmutables por run.
- [ ] Implementar activación compare-and-swap y rollback.
- [ ] Crear API administrativa protegida: status, validate, create revision,
      activate y rollback.
- [ ] Crear scripts `curl`/PowerShell sin exposición de secretos.
- [ ] Añadir `LISTEN/NOTIFY`, reconexión y reconciliación lenta en un incremento
      posterior al funcionamiento con una réplica.
- [ ] Añadir tests de activación concurrente, revisión inválida y notificación
      perdida.

**Acceptance:** C, D, T y U.

## T7: Governed LLM Access and per-run Agent factory

- [ ] Introducir `LLMAccess` como única frontera de inferencia.
- [ ] Implementar `ExecutionContext` y propagación mediante `ContextVar`.
- [ ] Crear Agent por run con ID lógico estable, `run_id` explícito y config
      snapshot fija.
- [ ] Implementar `GovernedModel`/adaptador que exija contexto y falle cerrado.
- [ ] Propagar `traceparent`, `correlation_id`, `llm_call_id` y revisión.
- [ ] Registrar usage, request IDs, latencia y error class.
- [ ] Mantener temporalmente OpenRouter directo solo detrás de `LLMAccess`.
- [ ] Cambiar el default de `AGENT_TOOL_CALL_LIMIT` y el fallback del factory a
      12; actualizar tests y documentación operativa en ese incremento.
- [ ] Configurar retries de Agent y Model explícitamente a 0.

**Acceptance:** Q parcial, X e Y.

## T8: Execution budget

- [ ] Implementar deadline total de 120 segundos.
- [ ] Limitar a 6 model calls lógicas y 8 Gateway requests por update.
- [ ] Limitar a 2 intentos Gateway por llamada lógica.
- [ ] Integrar tool hooks de Agno y el hard ceiling de 12.
- [ ] Calcular fingerprints HMAC de tool + argumentos canónicos.
- [ ] Bloquear repetición posterior a éxito y acotar retries tras error.
- [ ] Hacer los contadores seguros frente a tools async concurrentes.
- [ ] Implementar estimación/reserva/reconciliación de coste.
- [ ] Detener el run de forma controlada con estado y telemetry explícitos.

**Acceptance:** G y H.

## T9: Document extraction port

- [ ] Definir `DocumentExtractionPort` fuera de Agno.
- [ ] Eliminar la creación directa de `agno.agent.Agent` en el dominio.
- [ ] Implementar un adaptador de extracción mediante `LLMAccess`.
- [ ] Compartir config, deadline, contadores, coste y trace del run principal.
- [ ] Registrar provider/model reales en `ai_extractions`.
- [ ] Sustituir el `except Exception: pass` por resultado controlado y metadata
      observable sin exponer contenido.

**Acceptance:** P.

## T10: OpenTelemetry and privacy

- [ ] Desactivar telemetría de producto con `Agent(telemetry=False)`,
      `AgentOS(telemetry=False)` y `AGNO_TELEMETRY=false`.
- [ ] Añadir logs JSON estructurados con `correlation_id`.
- [ ] Instrumentar admission, queue, Agent, LLM, tools, budget y delivery.
- [ ] Exponer métricas agregadas de volumen, latencia, tokens, coste, errores,
      retries, fallbacks, rate limits y circuit.
- [ ] Desplegar OpenTelemetry Collector upstream como servicio privado Railway.
- [ ] Configurar allowlist/redaction, memory limiter, batch y cola/retry acotados.
- [ ] Exportar por OTLP a Grafana Cloud.
- [ ] Propagar W3C `traceparent` hacia LiteLLM.
- [ ] Crear tests que fallen si logs/traces contienen contenido sensible.
- [ ] Crear dashboards y alertas iniciales.

**Acceptance:** I, R y S.

## T11: LiteLLM Proxy pilot

- [ ] Provisionar PostgreSQL Railway dedicado para LiteLLM.
- [ ] Desplegar LiteLLM como servicio privado, con imagen/version digest fijado.
- [ ] Desactivar Swagger, Redoc y OpenAPI en producción.
- [ ] Crear virtual key exclusiva para AncoraMind/environment.
- [ ] Mantener provider keys y master key únicamente en Railway secrets.
- [ ] Crear aliases lógicos versionados.
- [ ] Configurar OpenRouter como upstream con fallback interno.
- [ ] Mantener inicialmente retries y cross-model fallback de LiteLLM a 0.
- [ ] Verificar fail closed y ausencia de bypass.
- [ ] Ejecutar benchmark p50/p95/p99 y TTFT frente a OpenRouter directo.
- [ ] Revisar advisories y superficies de administración antes de producción.

**Acceptance:** Q completo.

## T12: Reliability and cost governance

- [ ] Configurar cooldown/circuit y probar `CLOSED/OPEN/HALF_OPEN`.
- [ ] Aplicar RPM, TPM y max parallel requests por virtual key/ruta.
- [ ] Persistir spend logs y coste real/estimado sin contenido.
- [ ] Configurar budgets por route, día y mes.
- [ ] Alertar al 60%/80% y hacer hard stop al 90% del límite externo.
- [ ] Mantener el hard limit de OpenRouter al 100%.
- [ ] Verificar qué intentos internos expone OpenRouter para evitar falsa
      contabilidad.
- [ ] Evaluar un único retry o fallback cross-model futuro solo con datos y sin
      superar el attempt budget.

**Acceptance:** E y F.

## T13: Hardening, runbooks and closure

- [ ] Ejecutar load tests y duplicados concurrentes.
- [ ] Ejecutar crash injection y reinicios/deploys durante cada estado.
- [ ] Validar E2E Telegram completo en Railway.
- [ ] Probar rotación de admin token, payload key, LiteLLM key y credenciales OTLP.
- [ ] Validar retención/borrado y acceso a Grafana Cloud.
- [ ] Crear runbooks de Gateway down, circuit open, budget exhausted,
      `failed_ambiguous`, Collector down y rollback de config.
- [ ] Ejecutar unit tests, integration tests, Ruff y checks de migración.
- [ ] Completar `verification.md` con evidencia real.
- [ ] Actualizar BACKLOG, AGENTS, README y deployment docs al estado implementado.
- [ ] Cerrar BL-23 solo cuando la matriz A–Y esté verificada.
