# BACKLOG — AncoraMind

> Lista viva y priorizada de trabajo pendiente. Fuente única de verdad para
> "qué queda por hacer". Los `specs/*/tasks.md` son el registro histórico de
> "qué se hizo" (no editarlos una vez completados).
>
> Convención: cuando un item pasa a "en curso", se le asigna un número de spec
> (`specs/00X-...`) y se trabaja con SDD (spec.md → tasks.md → implementación).
> Al completarse, se tacha aquí con fecha y se enlaza su spec.

Última actualización: 2026-10-03

---

## Estado actual (snapshot)

| Milestone | Estado |
|---|---|
| M1 Agent Runtime (Telegram+Agno+session) | ✅ |
| M2 Canonical Memory (notes) | ✅ |
| M3 Document Memory (storage+extraction) | ✅ (specs/003 documentada retroactivamente) |
| M4 Vehicle vertical slice | ✅ |
| M5 Calendar & Reminders | ✅ |
| BL-21 Listas TODO multi-lista | ✅ (toda mutación gobernada — specs/011) |
| BL-8 Evals agentic | 🔶 27 casos sintéticos, runner estático, harness aislado y adaptador físico (sin inferencia real) implementados; pendiente ejecución LLM real (T7) y scoring semántico (T8) — specs/014 + 018 |
| BL-18 Sustituir ngrok por Railway | 🔶 Servicio, dominio HTTPS, webhook y healthcheck reales validados en Railway; falta activar Wait for CI y completar E2E Telegram M3–M5 — specs/008 |
| BL-23 Governed LLM Access, Telegram admission y OTel | 🔶 T2–T14 implementados; fase 6 validada en Railway (2026-09-19); candidato GPT-6 Luna `r3` preparado localmente (2026-09-28), pendiente publicación/activación remota; además queda verificar matriz A–Y completa — specs/013 |
| BL-25 Script E2E nativo PowerShell | ✅ Validación/configuración y flujo local/remoto implementados — specs/015 |
| BL-33 Health signals + dashboard de salud | 🔶 en curso — specs/016 (fase 2 del análisis de observabilidad 2026-09-23) |
| BL-38 Conversión de documentos (texto PDF/DOCX + export Markdown→PDF) | 🔶 Fase 1 (PDF texto determinista) implementada localmente; Fases 2-3 bloqueadas por BL-35/BL-29 — specs/021 |
| BL-39 Seguridad LLM ante prompt injection | 🔶 P0 consentimiento implementado (flag apagado en producción); frontera `untrusted_results` cubre documentos/notas/vehículos/recordatorios/calendario/TODOs; pendiente confirmaciones WRITE, adjunto directo al Agent, evals reales — specs/022 |
| BL-40 Remediación de auditoría técnica (2026-10-02) | 🔶 Fases 1–3 implementadas localmente (Fase 1: verificación Railway pendiente, servicio pausado); Fases 4–6 completas (consentimiento gobernado, zona horaria, sincronización documental) — specs/023 |
| BL-41 Recurrencia en calendario/recordatorios + snooze | 🔶 implementado localmente (684 unit + 94 integration verdes); pendiente validación E2E Telegram con el propietario — specs/024 |
| BL-42 Recuperación semántica documental | 🔶 implementado localmente con pgvector y embeddings gobernados; pendiente publicar/autorizar `ancoramind-embeddings-r1` y validación E2E — specs/026 |
| BL-43 Pantalla de administración centralizada | 🔶 implementado localmente (invitaciones, runtime-config, salud, enlaces); pendiente validación manual en Railway — specs/027 |
| BL-44 Parada de emergencia manual para Agent/LLM | 🔶 pendiente de diseño (surgió al definir BL-43; requiere revisar la matriz A–Y de specs/013 antes de tocar LLMAccess) |
| MVP usable | 🔶 E2E en curso (M1–M2 + M3 txt validados en Railway; M3 visión y M4–M5 pendientes — BL-1) |

Tests: 684 unit + 94 integration — Ruff y `mypy src/` limpios en
`src/ tests/ scripts/ migrations/`

---

## P0 — Hardening transversal de ejecución e inferencia

### BL-40 · Remediación de auditoría técnica (2026-10-02) 🔶 en curso — specs/023

Auditoría de coherencia especificación/implementación (2026-10-02) detectó 8
hallazgos accionables, organizados en 6 fases con orden de ejecución explícito
en `specs/023-audit-remediation/tasks.md`:

1. **🔴 Crítico — API REST de AgentOS expuesta sin autenticación.** `/config`,
   `/memories`, `/agents/*/runs`, `/sessions`, `/docs`, `/openapi.json`
   accesibles sin credencial en la configuración actual (confirmado por
   inspección local de `app.openapi()`; pendiente confirmar contra Railway
   real antes de cerrar). Posible bypass completo de admission/gobernanza.
2. **🟠 Alto — `UserContext` con fallback silencioso + `APP_ENV` insegura por
   defecto.** Identidad puede degradar a `"unknown"`; `APP_ENV=development`
   (default actual) desactiva la validación del secret de webhook en Agno.
3. **🟠 Alto — Fuga de sesiones DB + UUID sin validar en tools.** Ninguna
   tool cierra `get_session()`; varios `UUID(...)` sin capturar y mensajes
   de error que exponen detalle interno (`str(e)[:200]`).
4. **🔴 Crítico — Consentimiento de mutaciones mediado por el LLM.**
   `execute_*`/`remember_note` no verifican una confirmación nueva atribuible
   al usuario tras una entrega verificada; `mark_executed` no exige
   `status='confirmed'`. **Resuelto (2026-10-02):** T6b/T7 de
   `specs/022-llm-input-trust/consent-design.md` implementados en Fase 4
   (T4.1–T4.8) detrás de `GOVERNED_CONSENT_ENABLED` (apagado por defecto).
5. **🟠 Alto — Zona horaria naive en recordatorios/calendario.** Fechas sin
   tz se persisten asumiendo UTC; un recordatorio a "las 17:00" puede
   disparar 1-2h tarde/pronto según DST. **Resuelto (2026-10-03):** Fase 5
   completa — `resolve_user_timezone()`/`to_utc()`/`to_local_display()` en
   `src/domain/preferences/timezone.py`, normalización en los servicios de
   reminders/calendar, display convertido de vuelta en las tools,
   `get_current_datetime` devuelve también hora local.
6. **🟡 Medio — Sincronización documental.** Recuentos de tests desfasados,
   specs marcados "pendiente" ya implementados, tablas de capabilities
   obsoletas en `docs/architecture.md`, prompts con contrato JSON que
   ninguna tool implementa, código muerto (`src/agent/context.py`,
   `src/services/`, `src/governance/` vacíos). **Resuelto (2026-10-03):**
   Fase 6 completa — recuentos y `> **Status:**` actualizados, tabla de
   capabilities sincronizada con README, contrato de tools reescrito al
   formato real, `src/agent/context.py` y `src/services/` eliminados
   (`src/governance/` se mantiene — está documentado como reservado),
   hallazgo adicional corregido: `skills/calendar.md` existía pero nunca se
   cargaba en `assemble_instructions()`.

**Orden de ejecución:** fase 1 → 2 → 3 → 4 → 5 → 6 (fase 4 depende de fase 3;
el resto son independientes y priorizadas por riesgo).

**Decisiones aprobadas (2026-10-02):**
- **T1.2:** intentar primero quitar las rutas REST de AgentOS que no usamos
  (preferida); si no es viable técnicamente, caer a `OS_SECURITY_KEY` como
  fallback — documentar cuál se aplicó.
- **T4.7:** `analyze_document` sigue siendo automático (enviar un documento
  ya es la señal de intención de guardarlo — mejor UX, excepción aprobada a
  la regla WRITE). A cambio se añade `propose_document_delete`/
  `execute_document_delete`, que hoy no existe, para el caso "no quiero
  esto guardado".
- **T5.1:** zona horaria fija (`Europe/Madrid`) para toda la app por ahora,
  pero el código accede a ella solo a través de una función
  `resolve_user_timezone()`, lista para pasar a configuración por usuario en
  el futuro sin tocar tools/servicios. Se descarta guardar un offset
  numérico (se rompe con el cambio de hora estacional).

**Fase 1 implementada localmente (2026-10-02):** `AgentOS` no permite omitir
routers selectivamente ni `OS_SECURITY_KEY` nativo es reusable sin romper
`/admin/*`/`/health/readiness` (su exclusión por defecto no cubre rutas
propias) — se implementó un middleware propio
(`src/agent/agent_os_rest_guard.py`) que exige bearer solo en las rutas REST
de Agno, dejando intactas `/telegram/*`, `/admin/*`, `/health*`. Fail-closed:
`APP_ENV != "development"` sin `AGENT_OS_SECURITY_KEY` impide arrancar.
`/docs`/`/redoc`/`/openapi.json` cerrados fuera de development. 8 tests
nuevos, 560 unit passing, Ruff/mypy limpios. **Pendiente:** T1.1/T1.5
(verificación contra Railway) bloqueadas — el servicio está pausado;
retomar cuando se reanude.

**Fase 2 implementada localmente (2026-10-02):** `UserContext` ya no degrada a
`"unknown"` ni usa un `session_id` arbitrario como identidad (fail-closed con
`ValueError`). `APP_ENV` pasa a `production` por defecto; fuera de development
la app no arranca sin `AGENT_OS_SECURITY_KEY` ni
`TELEGRAM_WEBHOOK_SECRET_TOKEN`. `tests/conftest.py` declara
`APP_ENV=development` para las suites. 570 unit + 71 integration passing,
Ruff/mypy limpios. **Antes de reanudar Railway:** añadir
`AGENT_OS_SECURITY_KEY` a las variables del servicio.

**Fase 3 implementada localmente (2026-10-02):** las 32 tools cierran sus
sesiones de BD con `@closes_sessions`, también cuando fallan (antes cada
llamada dejaba una conexión del pool sin devolver). `source_document_id` se
valida antes de tocar la BD, y los errores inesperados devuelven un mensaje
fijo y solo registran la clase de la excepción. 585 unit + 71 integration
passing, Ruff/mypy limpios.

**Fase 4 — T4.1/T4.2 implementadas localmente (2026-10-02):** migración
`0006_proposal_consent` con el modelo de estados de `consent-design.md`
(`pending_confirmation → confirmed → executing → executed | failed_*`, más
`expired`/`discarded`), CHECK de estados e índice único que impide que un «Sí»
autorice dos propuestas. El repositorio añade el claim atómico (bloqueo de
fila, reloj de la BD, hash del payload, sin commits propios) y corrige
`mark_executed`, que antes sobrescribía cualquier estado. Las propuestas
antiguas sin procedencia no son ejecutables. 590 unit + 89 integration
passing (incluida una carrera real entre dos sesiones).

**Fase 4 — T4.3/T4.4 implementadas localmente (2026-10-02):** detrás de
`GOVERNED_CONSENT_ENABLED` (apagado por defecto), el procesador reconoce
botones Sí/No y el «Sí» escrito **antes** de llamar al Agent, y el Core añade
un bloque fijo con esos botones a cada propuesta que un run crea, generado
desde los datos guardados y no desde las palabras del modelo. La propuesta
solo queda confirmable tras verificar que Telegram entregó ese mensaje.
Probado de extremo a extremo con PostgreSQL real (propuesta → entrega con
botones → confirmación por botón). **Pendiente:** `answerCallbackQuery` (el
botón no deja de mostrar su reloj de carga todavía).
605 unit + 91 integration passing.

**Fase 4 — T4.5 implementada localmente (2026-10-02):** las 6 tools
`execute_*` ya no llaman a `confirm()` directamente. Nuevo
`confirm_or_use_confirmed()`: con el flag apagado se comporta igual que
antes (el LLM sigue "confirmando"); con el flag encendido, si la propuesta
ya quedó `confirmed` por el claim pre-Agent de T4.3, la tool la ejecuta sin
que el LLM la autorice. Se eligió esta vía "con reserva" en vez de quitar
`confirm()` del todo, porque sin ella el bot se habría roto mientras el
flag siga apagado (que es como está hoy en producción). 605 unit + 93
integration passing.

**Fase 4 — T4.6 implementada localmente (2026-10-02):** `remember_note`
escribía directamente desde la llamada del LLM, sin ActionProposal ni
confirmación — era la última excepción a la regla WRITE de AGENTS.md §2.4.
Sustituida por `propose_note`/`execute_note` con el mismo patrón que el
resto de tools: proponer no escribe, ejecutar exige confirmación (vía
`confirm_or_use_confirmed`, igual que T4.5). 32→33 tools registradas.
609 unit + 93 integration passing.

**Fase 4 — T4.7/T4.8 implementadas localmente (2026-10-02):** el hueco real
de T4.7 (no existía ninguna tool para borrar un documento) se cerró con
`propose_document_delete`/`execute_document_delete` (DESTRUCTIVE,
propose/confirm). 33→35 tools registradas; `prompts/skills/documents.md`,
`README.md`, `docs/architecture.md`, `docs/governance.md` y `AGENTS.md`
actualizados. T4.8 añadió 8 tests parametrizados que confirman que cada
`execute_*` (incluyendo las dos tools nuevas) se niega a mutar cuando
`confirm_or_use_confirmed` devuelve `None`; las ramas de carrera real ya
estaban cubiertas por T4.1/T4.2 contra PostgreSQL. Al revisar el inventario
de `consent-design.md` se encontró que **`/new` nunca invalidaba las
propuestas pendientes del chat**: `discard_pending_for_chat` existía desde
T4.1 pero `_handle_command` no lo llamaba, dejando una propuesta confirmable
con «Sí» tras resetear la conversación. Corregido (best-effort, no bloquea
la respuesta de `/new`) con un test de integración end-to-end nuevo.
622 unit + 94 integration passing.

**Fase 4 — T4.9 ejecutada (2026-10-02), Fase 4 completa (T4.1–T4.9):**
`ruff check`, `mypy src/`, `pytest tests/unit/`, `pytest tests/integration/`,
`python scripts/run_evals.py` y `git diff --check` en verde (622 unit + 94
integration; evals 27 casos/6 categorías tras corregir una referencia
obsoleta a `remember_note` en `evals/security/cases.json`). Actualizados
`specs/022-llm-input-trust/tasks.md`/`verification.md`/`spec.md`,
`docs/llm-security-hardening.md` y las entradas de BL-39 más arriba, que
describían el consentimiento como diseño sin implementar — ya está
implementado y probado contra PostgreSQL real, detrás de
`GOVERNED_CONSENT_ENABLED` (apagado por defecto en producción; activarlo no
es parte de esta fase).

**Prioridad P0** junto a BL-39 (fase 4 es su implementación pendiente).
Ver `specs/023-audit-remediation/`.



### BL-39 · Seguridad ante prompt injection y contenido de menor confianza 🔶 en curso — specs/022

Revisar la frontera adjuntos/notas/extracciones/resultados de tools → Agent,
priorizando autorización de mutaciones en Core y confirmación atribuible a un
evento nuevo del usuario y a la propuesta concreta (no al criterio del LLM).
**Hecho (2026-10-02, specs/023 Fase 4):** WRITE directos (antes `remember_note`,
hoy `propose_note`/`execute_note`) y los 8 `execute_*` ya exigen esa
confirmación, detrás de `GOVERNED_CONSENT_ENABLED` (apagado en producción).
Después, endurecer la preparación local de adjuntos y la representación de

contenido/filenames/`suggested_actions` no confiables, incluido el paso directo
de medios al Agent y las lecturas posteriores. El antiguo fence
`<document_data>` no era una frontera de seguridad; la serialización JSON
introducida en specs/022 tampoco autoriza operaciones. Coordinar con BL-38 /
specs/021 los ensayos pendientes antes de ampliar la extracción de texto PDF.

Ampliar evals sintéticas y probarlas contra el Agent gobernado (BL-8/specs/018)
con tools simuladas; comparar detectores locales offline y falsos positivos
antes de añadir dependencias. No hay RAG/vector search hoy: si se introduce,
aplicar controles tanto en ingesta como en recuperación. Mantener privacidad
metadata-only (ADR-006) y todo acceso inferencial a través de `LLMAccess`.
**Prioridad P0** para consentimiento/WRITE; **P1** para la frontera documental
y de tools; **P2** para pilotos de detectores. Detalle, hipótesis y criterios de
cierre: `docs/llm-security-hardening.md` y `specs/022-llm-input-trust/`.
**Primer incremento local (2026-09-29):** instrucciones de extracción en
`prompts/`, fuente documental serializada en JSON con filename/texto acotados,
prompt versionado 1.2 y `suggested_actions` ya no devuelto en respuestas de
tools documentales. **No resuelve el P0 de consentimiento**, ni protege aún
adjuntos entregados directamente al Agent o notas/resultados de otras tools.
**Diseño P0 (2026-09-30):** `specs/022-llm-input-trust/consent-design.md`
define UX de confirmación inequívoca, entrega previa, caducidad de 15 minutos,
consumo único, estados y fallos ambiguos; inventaría ejecutores, WRITE directos
y ruta AgentOS heredada.
**Implementado y validado con PostgreSQL real (2026-10-02):** T6b/T7 del
diseño P0 se completaron en `specs/023-audit-remediation` (T4.1–T4.8), detrás
de `GOVERNED_CONSENT_ENABLED` (apagado por defecto en producción). Detalle en
`specs/022-llm-input-trust/verification.md` §"P0 — implementado" y en BL-40.

**Punto 1 implementado localmente (2026-10-03, specs/022 T8 segundo
segmento):** el envoltorio `untrusted_results` (acotado/truncado/marcado
`trust: "untrusted_data"`) que ya cubría `search_documents`/`get_document`/
`search_notes` se extiende a las tools de lectura restantes: `find_vehicle`,
`get_vehicle_summary`, `get_vehicle_maintenance_history` (vehículos.py),
`list_reminders` (reminders.py), `check_calendar` (calendar.py) y
`list_todo_lists`/`list_todo_items` (todos.py) — ninguna existía con tests de
tool antes de este incremento, así que se crean `test_vehicle_tools.py`,
`test_reminder_tools.py`, `test_calendar_tools.py` y se ampliá
`test_todos_tools.py` (18 tests nuevos, 723 unit passing). `MAX_RESULT_RECORDS`
aplicado donde no había límite de registros (`get_vehicle_maintenance_history`
devolvía el historial completo sin cap). `prompts/tool_contract.md` corregido
— afirmaba "never JSON"/"don't parse the reply as JSON" cuando
`search_documents`/`get_document`/`search_notes` ya devolvían el envoltorio
desde specs/022; ahora documenta ambas formas de respuesta. **Alcance
explícitamente fuera de este incremento** (ver `docs/llm-security-hardening.md`
§3 y `specs/022/tasks.md` T8): las respuestas de confirmación
`propose_*`/`execute_*` (ecoan contenido en el mismo turno en que el usuario
lo escribió, riesgo distinto al de datos de terceros recuperados después), el
adjunto original entregado directamente al Agent principal (no solo su
extracción) y la ruta AgentOS legada.

### BL-23 · Governed LLM Access, Telegram Admission and Observability 🔶 T2–T14 implementados localmente — specs/013 + ADR-004/005/006

Convertir el acceso a LLM y la entrada Telegram en capabilities gobernadas:

```text
Telegram → admission/idempotency → Agno → logical route
→ LiteLLM Proxy → OpenRouter → provider/model
```

Incluye idempotencia durable por `update_id`, semántica at-most-once del Agent,
private-chat/allowlist reales, rate/concurrency limits, execution budget,
configuración runtime versionada y cacheada, rutas lógicas, LiteLLM privado y
fail closed, coste/circuit breaker, y OpenTelemetry Collector + Grafana Cloud.
La telemetría de producto de Agno está desactivada con la observabilidad propia.
Defaults aprobados: 120 s, 6 model calls, 12 tool calls como hard safety
ceiling, 8 requests Gateway y concurrencia global 2.

**Estado (2026-09-24):** T2 aporta Alembic y el schema reproducible. T3 aporta el
ledger reusable: identidad durable `UNIQUE(bot_id, telegram_update_id)`, auditoría
de cada delivery Railway, `correlation_id` estable, claim atómico
`accepted → agent_started`, payload Telegram normalizado/cifrado con Fernet y
purga por retención. T4 instala, detrás de `TELEGRAM_ADMISSION_ENABLED=false` por
defecto, el endpoint propio estable: secret, private-chat, allowlist fail-closed,
deduplicación durable, rate/cola PostgreSQL y `2xx` solo tras commit. T5 debe
conectar el processor/Agent al claim; mientras tanto el rollout flag no se activa
en producción. **Actualización T5:** processor in-process auto-gated que reclama
`accepted`, aplica locks chat/usuario + semáforo global 2, persiste outbox cifrada
antes de delivery, refresca `typing` sin streaming y marca estados post-efecto
como `failed_ambiguous` tras restart. **Actualización T6:**
control plane runtime con schemas cerrados `extra="forbid"`, checksum SHA-256,
revisiones inmutables, CAS con conflicto `409`, bootstrap sin secrets,
snapshot in-memory last-known-good y API administrativa Bearer con actor
obligatorio. `LISTEN/NOTIFY` queda para un incremento posterior con una réplica.
**Actualización T7:** el processor gobernado captura snapshot y contexto por run,
compone un Agent por run con `run_id` explícito, retries 0 y ceiling 12; cada
model turn pasa por `LLMAccess`/`GovernedModel` y persiste metadata de uso sin
contenido personal. El provider directo sigue limitado a esta frontera hasta
LiteLLM/T11; la extracción documental se migra en T9 y AgentOS legado persiste
solo mientras T4/T5 sigan apagados. **Actualización T8:** el budget aplica
deadline de 120 s, techos de model/Gateway calls, límite de 12 tools, HMAC de
argumentos canónicos y bloqueo de repetición; `StopAgentRun` corta el loop tras
una tool rechazada. Pricing opcional versionado permite coste estimado/real sin
I/O por call; agotamiento queda auditado como `failed_ambiguous` sin replay. **Actualización T9:** la extracción documental ya
no crea `agno.agent.Agent` en el dominio: `DocumentService` usa el port
`DocumentExtractionPort`, cuyo adaptador Agno pasa por `LLMAccess`. Dentro de un
run gobernado comparte snapshot, budget, coste y trace (el usage se audita bajo
la interacción); en el path AgentOS legado usa un contexto bootstrap standalone
sin filas de usage (no existe interacción referenciable). `ai_extractions`
registra provider/model reales y los fallos dejan metadata observable sin
contenido. **Actualización T10:** Agno product telemetry queda desactivada en
Agent, AgentOS, entorno local y Docker. `src/observability/` emite JSON y OTel
metadata-only con allowlist; el exporter OTLP al Collector privado es opcional y
fail-open. El manifiesto `observability/otel-collector.yaml` aplica redacción,
memory limiter, batch y cola/retry antes de Grafana. Falta crear el servicio
Collector privado y dashboards/alertas en Railway mediante rollout explícito. **Actualización T11:** el pilot del LiteLLM Gateway está implementado y
validado localmente: `gateway/` fija la imagen por digest, expone sólo los
aliases versionados, desactiva Swagger/Redoc/OpenAPI (404 verificado) y mantiene
retries/fallbacks en 0. Con `LITELLM_PROXY_ENABLED=true`, `LLMAccess` y el
AgentOS legado componen únicamente `OpenAILike` hacia el Gateway privado con la
virtual key exclusiva (`scripts/litellm_create_virtual_key.py`); fail-closed
verificado con el Gateway real (key inválida ⇒ 401 del Gateway; upstream dummy ⇒
401 sin bypass). Falta el rollout Railway (PostgreSQL dedicado + servicio
privado), el benchmark con clave real y la revisión de superficie productiva.
**Actualización T12:** implementada la gobernanza de coste y fiabilidad:
`CostGovernanceConfig` (límite externo + umbrales 60/80/90 + budgets día/mes/ruta)
con invariante en rutas de pago; el runner evalúa el spend al inicio del run
con hard stop `failed_controlled` sin replay; el Gateway declara circuit
breaker (`allowed_fails`/`cooldown_time`, transiciones CLOSED/OPEN/HALF_OPEN
validadas localmente) y RPM/TPM por alias + por virtual key (enforcement 429
verificado); retries/fallbacks mantienen 0 por decisión documentada.
**Actualización T13:** hardening verificable localmente —
`tests/integration/test_hardening_013.py` (20 duplicados → 1 claim, burst
ordenado exactamente-once, crash tras `agent_started`/`delivery_started` →
`failed_ambiguous` sin replay/reenvío, `response_ready` recuperable, purga de
retención, orden estable) — y runbooks operativos en `docs/runbooks-013.md`.
**Actualización rollout Railway (2026-09-16):** Supabase canónico migrado a
Alembic head `0003_telegram_admission_indexes`, LiteLLM privado + Postgres +
Redis co-localizados en `europe-west4-drams3a`, sin dominio/TCP proxy; la app
opera fail-closed con virtual key exclusiva. T4 admission y T5 processor están
activos y un update E2E real quedó trazado por `correlation_id`, con outbox
cifrada, delivery Telegram completada y un uso LiteLLM persistido. El commit
`086f1fa` corrigió además la sincronización transaccional del resumen de uso
(`config_revision`, model/Gateway counts y costes) y pasó CI completo.
**Actualización paso 1 Railway (2026-09-18):** duplicados y negativas
validados con updates sintéticos: `978199899` reenviado 2 veces →
1 interacción `completed` (`8dc1bbe3-05b7-43c8-b947-9d0ac20d0142`,
model=1/gw=1, segunda delivery `duplicate=true`, cero IA extra);
grupo `978199900` → `rejected`/`non_private_chat` e intruso `978199901` →
`rejected`/`user_not_allowlisted`, ambos `200` con cero IA (A/B/V/N/O ✅).
**Actualización cambio de modelo en caliente (2026-09-18, ADR-005 enmendado):**
la enmienda documenta que la publicación del alias Gateway (decisión 9 /
`design.md` §11) nunca se había implementado —`RuntimeConfigManager.activate()`
sólo hacía el CAS en PostgreSQL— y fija una política aditiva: los aliases base
`*-r1` viven en `gateway/litellm-config.yaml` y nunca se mutan; un cambio de
modelo publica una generación nueva (`r2+`) en la BD del Gateway
(`store_model_in_db: true`) mediante `scripts/litellm_gateway_alias.py`
(`publish`/`grant`/`verify`/`retire`, con guards de alias base e idempotencia).
La vía de cambio sin redeploy queda implementada y verificada localmente
(T14 fases 1–5) y **validada en Railway el 2026-09-19 (fase 6)**: publicación
de `ancoramind-default-r2` en caliente (tras corregir `STORE_MODEL_IN_DB` de
`False` a `true`), `grant` aditivo, revisión runtime 2 activada con CAS,
mensaje real de Telegram con `effective_gateway_route='ancoramind-default-r2'`
(`config_revision=2`, `cost_source='pricing_snapshot'`) y ensayo de rollback
bidireccional a la revisión 1. Evidencia en `tasks.md` T14 fase 6.
Pendientes: caída/circuit del Gateway en Railway, Collector/Grafana +
dashboards/alertas, benchmark con clave real, reconciliación de costes y
rotación real. **BL-23 permanece abierto**
hasta verificar la matriz A–Y completa.
Ver `specs/013-llm-access-governance/`.

**Actualización rollout Collector/Grafana (2026-09-24):** el servicio
`ancoramind-otel-collector` existe en Railway como **staged-create** con source
`lealp22/ancoramind-app@main` y `dockerfilePath=observability/Dockerfile`
(Dockerfile nuevo que fija `otel/opentelemetry-collector-contrib:0.138.0` y
copia el manifiesto versionado; CI valida la config con valores dummy). Nada
desplegado: la patch está staged y **pendiente de `accept-deploy` con
confirmación explícita**. Bloqueos abiertos en este punto:
1. **Push a `origin/main` fallido (403 `Write access to repository not
   granted`)** — las credenciales HTTPS locales no tienen escritura; sin el
   push del Dockerfile en `main`, Railway no puede buildar.
2. **Secretos `GRAFANA_OTLP_ENDPOINT` / `GRAFANA_OTLP_AUTHORIZATION` sin
   crear** en el servicio Collector (stack Grafana Cloud pendiente de
   provisionar; la región del stack consta como "Pendiente" en
   `verification.md`).
3. **Región del servicio Collector en `us-west2`** mientras el resto del
   proyecto está en `europe-west4-drams3a`; el private networking funciona
   cross-region, pero debe alinearse en el dashboard antes del deploy (las
   herramientas de automatización disponibles no permiten cambiar región).
4. Tras deploy del Collector: añadir `OTEL_EXPORTER_OTLP_*` a la app
   (solo tras validar el Collector), verificar fail-open con `/health` y
   comprobar en Grafana que llegan únicamente atributos allowlisted.
Los pasos 1–4 bloquean el cierre de la matriz A–Y (entradas Collector/Grafana)
y, con ella, de BL-23; dashboards/alertas (BL-33/specs/016) consumen este
resultado.

**Criterio de cierre:** matriz A–Y de specs/013 verificada: un mismo update
ejecuta el Agent como máximo una vez, el modelo cambia sin redeploy, ningún run
supera su budget, LiteLLM falla cerrado, la interacción es trazable por
`correlation_id` y no se exporta contenido personal.

### BL-24 · Onboarding de usuarios Telegram mediante invitaciones gobernadas 🔶 en curso — specs/017
`ALLOWED_TELEGRAM_USER_IDS` permite una allowlist técnica, pero no es un proceso
práctico de alta para un grupo de evaluadores aún no definido: no se debe abrir
el bot a cualquier usuario ni pedir a cada persona que averigüe su Telegram ID.

Diseñar e implementar un flujo de **pairing gobernado**: un operador crea una
invitación/código temporal, de un solo uso o con cupo explícito; la persona lo
canjea en un chat privado con el bot; el backend muestra la solicitud al operador
y exige aprobación antes de vincular el `telegram_user_id` observado en el update
autenticado a una identidad/autorización durable. El código es una credencial de
onboarding, no un sustituto de los controles existentes de secret de webhook,
private-chat, rate limiting, idempotencia ni auditoría de BL-23.

Decidir en el spec el canal de emisión/solicitud (web mínima, herramienta/admin
CLI u otro mecanismo), el modelo de roles/grupos, aprobación/rechazo, expiración,
rotación, revocación inmediata y recuperación ante canje duplicado o concurrente.
Secretos/códigos deben almacenarse con hash, TTL y estado explícito; nunca se
registran en claro. Las operaciones administrativas y toda mutación de
autorización deben ser auditables con actor, timestamps y motivo. Mantener
fail-closed: una solicitud pendiente, rechazada, expirada o revocada no llega al
Agent. Añadir pruebas de replay, carrera de doble canje y revocación de una sesión
ya autorizada.

**Prioridad P0:** desbloquea pruebas controladas con múltiples personas y debe
integrarse con la admission durable de `specs/013`, no mediante un bypass de la
allowlist actual.

**Actualización 2026-09-27 (T1):** creado `specs/017-telegram-governed-pairing`
y la base auditable: migración Alembic `0005_telegram_pairing`, bootstrap
idempotente y API administrativa apagada por defecto (`TELEGRAM_PAIRING_ADMIN_ENABLED`)
que reutiliza bearer + actor obligatorio. Las invitaciones se generan con alta
entropía y se persisten sólo como HMAC con `TELEGRAM_PAIRING_CODE_PEPPER`; la
emisión devuelve el código una única vez. **Actualización T2:** el canje atómico
ya existe en Core (`FOR UPDATE` de invitación + advisory lock por usuario), aplica
TTL/cupo/estado/replay y crea como máximo una solicitud `pending` por usuario; la
cola administrativa permite listar/rechazar con actor/motivo. **Actualización T3:**
`TELEGRAM_PAIRING_ENABLED` activa `/pair <code>` sólo en chat privado; el código se
canjea antes del Agent, se redacta del payload durable y genera una respuesta fija
por outbox sin llamada LLM. Admission conserva `ALLOWED_TELEGRAM_USER_IDS` como
ruta técnica y además consulta la autorización durable activa en cada nuevo update,
por lo que una revocación bloquea el siguiente update sin reinicio. Validación local:
491 unitarias passing + 2 fallos ambientales conocidos de PowerShell/ruta con
espacios, y 71 integraciones passing; quedan T4 (runbook/flags de despliegue y
E2E Telegram/Railway controlado con cuenta no productiva). **Actualización T4
local:** `scripts/telegram_pairing.py` opera la API administrativa protegida
(emitir/listar/aprobar/rechazar/revocar) sin acceso SQL directo, y
`docs/runbooks-017-telegram-pairing.md` documenta flags, rotación, rollback y el
E2E controlado. Aún no se ha registrado/modificado un webhook ni contactado una
cuenta Telegram: esas acciones requieren aprobación explícita.

**Actualización 2026-10-05 (T5, incremento sobre BL-43):** con un solo
operador, exigir siempre una segunda aprobación manual tras el canje era un
punto único de disponibilidad (si el operador está incomunicado, nadie puede
empezar a usar AncoraMind aunque la invitación ya se haya compartido por un
canal de confianza). Se añade `auto_approve` como flag **opt-in** por
invitación (`false` por defecto, migración `0010_pairing_auto_approve`): si se
activa al emitir, el canje (`/pair <código>`) crea la autorización activa en
el mismo paso atómico que hoy crea la solicitud `pending`, sin segunda
intervención — el invariante "invitación ≠ autorización" sigue siendo la
regla por defecto, `auto_approve` es la única excepción, explícita y
auditable (queda registrado qué operador la activó y con qué motivo, igual
que una aprobación manual). Expuesto en los tres puntos de entrada: CLI
(`--auto-approve`), admin API (`CreateInvitationRequest.auto_approve`) y el
dashboard de BL-43 (checkbox con aviso del trade-off: el código pasa a ser el
único factor de confianza, combinarlo con un `max_uses` ajustado). Tests:
2 nuevos de integración (atomicidad de la autorización, E2E de admission con
la respuesta de outbox diferenciada) + unitarios de servicio/admin API/CLI.

---

## P1 — Cerrar el MVP (validación)

### BL-1 · E2E Telegram de M3–M5
Probar en Telegram con credenciales reales: subir documento → extracción,
registrar vehículo + mantenimiento (propose/execute), crear recordatorio y
evento de calendario (propose/execute).
**Pausa operativa (2026-09-07):** alerta de seguridad de red al usar ngrok;
no retomar el canal hasta disponer de una alternativa autorizada (BL-18).
Mientras tanto, validar los flujos mediante integration tests sin Telegram:
la capa de repositorios ya está cubierta (specs/009, 16 tests + fix jsonb);
los flujos service/tool con LLM real siguen requiriendo este E2E.
**Criterio de cierre:** los 5 flujos probados y documentados en el
`verification.md` del spec correspondiente.

**Actualización 2026-09-20:** diagnosticado el fallo de M3 en el processor
gobernado: normalizaba únicamente texto y descartaba adjuntos, por lo que una
imagen recibía `200` pero no respuesta. Corrección local implementada y cubierta:
referencias Telegram cifradas, descarga posterior al claim, tamaño/MIME acotados,
ingesta automática y renderizado PDF transitorio. La extracción visual selecciona
la ruta lógica `ancoramind-vision`; falta publicar `ancoramind-vision-r2` con
`openrouter/qwen/qwen3.6-35b-a3b`, activar una revisión runtime por CAS y repetir
el E2E real antes de marcar M3 como validado.

**Actualización 2026-09-20 (validación E2E txt ✅):** primer flujo E2E completo
validado en Telegram/Railway (BL-18 activo): documento .txt → archivado +
extracción IA persistida + respuesta con resumen en el chat. Tres capas de bug
corregidas y desplegadas: (1) prompt v1.1 sin contenido ni schema (commit
`25e8743`), (2) migración `0004_ai_extractions_schema` aplicada a prod — la tabla
pre-baseline carecía de `schema_version` (42703 en INSERT, commit `f77402d`),
(3) `model_dump()` en modo Python filtraba `datetime.date` no serializable a
JSONB — `TypeError` que mataba el run tras la inferencia pagada (commit
`86673c7`, `mode="json"`). Evidencia en prod: `telegram_interactions.status`
`completed`, fila en `ai_extractions` (prompt_version 1.1, confidence 0.96) y
usage event bajo la interacción. Pendiente en M3: ruta visión (imagen/PDF)
tras el rollout de Qwen r2; M4–M5 siguen pendientes de E2E.

**Actualización 2026-09-27 (bug de continuidad conversacional tras adjunto ✅):**
diagnosticado en producción vía Telegram: tras `analyze_document` procesar un
`.txt`, una pregunta de seguimiento en el mismo hilo ("¿qué vas a hacer con esta
información?") ignoraba por completo el documento — el LLM respondía sobre un
tema anterior no relacionado. Causa: `GovernedInteractionRunner.run()` invocaba
`analyze_document` directamente cuando había adjuntos, evitando `agent.arun()`;
solo `arun()` persiste el turno en la `AgentSession` que alimenta
`add_history_to_context`, así que el turno del documento nunca quedaba en el
historial. Corregido eliminando esa rama: ahora todo run (con o sin adjuntos)
pasa por `agent.arun(..., images=..., files=...)`, dejando que Agno invoque
`analyze_document` como tool call normal y registre el turno. Tests actualizados
en `test_governed_interaction_runner.py`; 506 unit tests, ruff y mypy en verde.
Pendiente de re-validar en Telegram/Railway como parte del E2E de M3.

### BL-18 · Sustituir ngrok por Railway 🔶 en curso — specs/008
La alerta de tráfico tipo C2 hace no recomendable seguir usando ngrok en esta
red sin autorización. **Decisión (2026-09-08): Railway** como despliegue
gestionado conectado a GitHub; Supabase permanece como PostgreSQL y Storage.
Hecho: runtime compatible con `PORT`, Dockerfile, healthcheck, `railway.json`,
CI GitHub Actions, helper de webhook seguro y documentación. **Evidencia Railway
(2026-09-19):** servicio `ancoramind-app` en `production`, rama `main`, deployment
`SUCCESS` del commit `9d7999b`, dominio HTTPS estable
`https://ancoramind-app-production.up.railway.app`, `/health` → `200`, 34 variables
de producción y webhook Telegram registrado sin updates pendientes. LiteLLM sigue
privado sin dominio/TCP proxy.

**Pendiente:** el servicio tiene `checkSuites: false`, por lo que falta activar
**Wait for CI** (y decidir protección de `main`); también falta repetir y documentar
el E2E Telegram de M3–M5. Por esos criterios BL-18 **no está cerrado todavía**.
**Nota (2026-09-09):** al desplegar se activará también el worker de
recordatorios (BL-5 / ADR-003 / specs/010): variables `REMINDER_WORKER_*`
opcionales (defaults válidos); su entrega es **outbound** y funciona desde el
primer deployment saludable, sin esperar al registro del webhook. Ver
`docs/deployment-railway.md` §8.
**Criterio de cierre:** dominio HTTPS Railway estable, CI/CD operativo y E2E
Telegram ejecutado sin alertas ni túneles desde el equipo local.

### ~~BL-25 · Script E2E nativo para PowerShell~~ ✅ implementado — specs/015 (2026-09-19)
`scripts/run-e2e.ps1` ofrece `-Check`, `-Reset`, carga literal y segura de `.env`,
validación de provider/Storage/DB/Gateway, PostgreSQL local + bootstrap, ngrok y
webhook para flujo local. `-PublicBaseUrl` registra el webhook contra un dominio
HTTPS desplegado (Railway) sin iniciar ngrok, Docker ni la app local. Tests cubren
configuración válida, provider inválido, `.env` no ejecutable y URL pública con
path rechazada. Ver `specs/015-powershell-e2e/verification.md`.

### BL-22 · Migrar reminder worker a FastAPI lifespan ✅ implementado — specs/012
`src/main.py::_register_reminder_worker` usa `app.add_event_handler(...)`,
que la versión instalada de FastAPI ya no expone (`AttributeError` al
importar `src.main` con worker habilitado — detectado 2026-09-10 durante
BL-21). Migrar a `lifespan` (`@asynccontextmanager`, pasado a
`FastAPI(lifespan=...)` o al `AgentOS.get_app()` si lo soporta): arrancar
`asyncio.create_task(worker.run_forever(...))` al entrar y cancelarlo
limpiamente al salir. Mantener los auto-gates actuales
(`REMINDER_WORKER_ENABLED` + `ANCORA_DATABASE_URL` + `TELEGRAM_TOKEN` con
sus logs de motivo). **Criterio de cierre:** `python -c "from src.main
import app"` sin `AttributeError` (con worker habilitado y deshabilitado);
suites unit + integration verdes; Ruff limpio. Toca `main.py` + tests del
wiring (nuevo o existentes de specs/010). **Prioridad P1** — sin esto la app
no arranca con el worker activo (regresión vs specs/010).
**Hecho (2026-09-10):** `src/agent/lifecycle.py` envuelve el lifecycle previo
de AgentOS/Starlette, preserva los tres auto-gates, crea la task por instancia
en `app.state` y la cancela limpiamente; `main.py` ya no usa
`add_event_handler` ni estado global. 3 tests de lifecycle; 171 unit passing,
Ruff y mypy del alcance limpios; integración ejecutada sin fallos pero omitida
sin PostgreSQL/Docker. Ver `specs/012-fastapi-lifespan/`.

### BL-33 · Health signals + Dashboard de salud 🔶 en curso — specs/016

Materializa la **fase 2** del análisis de observabilidad (2026-09-23): el
`/health` actual (AgentOS) sólo prueba que el proceso escucha. Se añade
`GET /health/readiness` (DB, reminder worker, interaction processor,
Gateway/circuit breaker, cola de admission, revisión de runtime config, edad
de la última interacción) y health metrics metadata-only por el pipeline OTel
existente, más el dashboard Grafana **versionado en
`observability/dashboards/`** con vista de salud a simple vista y alertas
(circuit open, spend, errores de delivery, heartbeat, silencio de tráfico).
Grafana Cloud permanece como backend (ADR-006). Fuera de este incremento: stack
OSS local (fase 3, diferida) y Langfuse (registrado como candidato BL-8).
El dashboard complementa —no sustituye— el rollout pendiente del
Collector/Grafana de BL-23.

---

## P2 — Funcionalidad para "usable de verdad"

### BL-6 · OCR/vision real para extracción de documentos 🔶 en curso
La extracción visual está implementada localmente: imagen directa o PDF renderizado
con PyMuPDF (máximo 3 páginas) → ruta lógica `ancoramind-vision` → salida
estructurada. Los contenidos siguen siendo DATA, no INSTRUCTIONS. Pendiente:
publicar/autorizar `ancoramind-vision-r2` con Qwen en Railway, activar la revisión
runtime, benchmark de precisión/coste/latencia y E2E Telegram con PDF e imagen.
**Nota triage TODO (2026-09-20):** los PDFs escaneados ya fluyen por la ruta
visual (PyMuPDF rasteriza páginas con o sin capa de texto — el "fallback OCR"
propuesto ya está cubierto por diseño). **Resuelto (2026-10-03, specs/021 Fase
1/BL-38):** `analyze_document` ya detecta la capa de texto (`has_extractable_text`)
y, cuando existe, usa `extract_pdf_text_markdown` (determinista, PyMuPDF/
pymupdf4llm) en vez de la ruta visual — PDFs digitales ya no pagan una llamada
de visión. Queda pendiente del benchmark: política explícita para PDFs de más
de 3 páginas (hoy ambas rutas comparten el mismo límite
`document_vision_max_pdf_pages`); OCR dedicado solo si la ruta visual no
alcanza precisión en escaneados.

### BL-7 · Proveedor de calendario real
Implementar un `CalendarProvider` real (Google Calendar, CalDAV o similar)
tras el Protocol existente. NoopCalendarProvider queda como default para dev.

### BL-26 · Notas de voz entrantes y transcripción gobernada (STT) 🔶 diseño en curso — specs/028
**Actualización 2026-10-06:** alcance acordado: notas de voz originales de hasta
**5 minutos**, respuesta textual y «Sí»/«No» por voz como alternativa de
consentimiento determinista, sin exigir teclear ni botones. El coste por nota
se deriva de duración y tarifa versionada (incluido redondeo/mínimo); no se pide
un presupuesto USD STT manual adicional, pero se conservan límites de gasto
agregado y presupuesto de interacción. `specs/028-telegram-voice-stt/` define
contratos propuestos, fases y matriz V01–V36; **runtime y aceptación voz pendientes**.
Dependencia para E2E de confirmación/ejecución: conectar `_execute_claimed()`
(BL-40/specs/023) y habilitar consentimiento gobernado sin bypass legacy.

Permitir que una nota de voz de Telegram se procese como un mensaje conversacional:
descargar el audio autorizado por Telegram, transcribirlo y pasar **solo el texto
resultante** al mismo flujo de admission/processor/Agent que usa un mensaje escrito.
El audio y su transcripción son datos personales no confiables. La transcripción
es el mensaje conversacional del usuario y puede expresar solicitudes funcionales;
se trata como input no confiable y nunca puede elevar permisos, modificar políticas
ni sustituir la identidad y confirmación resueltas por el Core. No se exporta a
logs/OTel y se somete a retención/cifrado equivalentes o más estrictos que el
payload Telegram de specs/013.

**Diseño requerido:** no crear clientes físicos de STT desde domain/services/tools.
Definir un `SpeechToTextPort` y una capability gobernada con ruta lógica versionada,
`RuntimeConfigSnapshot`, `ExecutionContext`, presupuesto por duración/tamaño, uso y
coste auditables, correlación y fail-closed. La descarga de `file_id` y conversión
del audio vive en la capa Telegram/agent; el dominio recibe un puerto y texto
transcrito etiquetado como DATA. Preservar `same bot_id + update_id => at most one
Agent execution`, incluidos fallos tras descargar/transcribir; no reintentar ni
reproducir automáticamente una transcripción ambigua. Definir límites explícitos
de duración, tamaño, MIME/codec y política para audio sin habla o ilegible.
El pipeline debe ser desacoplado y comprobable por etapas
(`accepted → downloaded → transcoding/transcribing → transcribed → agent_started`),
con estados durables suficientes para distinguir fallo seguro de resultado
ambiguo. Sus señales de progreso serán eventos internos tipados y metadata-only,
proyectados a la outbox por BL-32; ningún hook recibe o exporta audio/transcripción
salvo el componente autorizado que la necesita.

**Modelo inicial recomendado para benchmark:** `openai/whisper-large-v3-turbo`.
En OpenRouter figura con formatos habituales de Telegram (incluido `ogg`) y coste
de $0.000003/s (~$0.00018/min), muy inferior a `mistralai/voxtral-mini-transcribe`
($0.003/min), `microsoft/mai-transcribe-2` ($0.10/h ≈ $0.00167/min) y
`fish-audio/transcribe-1` ($0.0001/s = $0.006/min). Antes de fijarlo, comparar
exactitud y latencia con un corpus sintético/consentido de notas cortas en español,
ruido, nombres/matrículas y code-switching. MAI-Transcribe 2 es el candidato de
calidad/funcionalidad si hicieran falta diarización, timestamps por palabra o
keyword biasing; Voxtral Mini es alternativa intermedia. No usar modelos de chat
para STT ni bypass del Gateway/política de inferencia.

**Criterio de cierre:** E2E de nota de voz privada allowlisted → una sola
transcripción auditada → un solo Agent run → respuesta textual; rechazos de tipo,
tamaño/duración, usuario/grupo no autorizado y error STT no consumen Agent ni
dejan contenido en telemetría. Añadir unit, integration, evals y evidencia de
coste/latencia real antes de activar en producción.

**Prioridad propuesta: P2.** Puede subir a P1 tras cerrar BL-23, pues mejora de
forma directa el uso cotidiano del asistente.

### BL-27 · Respuestas de voz opcionales en Telegram (TTS) — análisis previo
**La respuesta textual ya está implementada:** el processor de specs/013 persiste
una `logical_response` cifrada y la entrega por `TelegramNotifier.send_text()` →
Bot API `sendMessage`. Por tanto, recibir voz y responder con texto no requiere
otra capability de salida.

Evaluar por separado la respuesta **hablada**: síntesis TTS del texto final,
entrega como `sendVoice`/`sendAudio`, preferencia explícita por usuario y fallback
a texto. Requiere decidir proveedor/modelo, idiomas/voces, coste/latencia, formato
Telegram, moderación de contenido, retención de audio, límites de longitud,
idempotencia de delivery y cómo persistir/auditar `response_kind='voice'` sin
guardar contenido en telemetría. Debe pasar por una capability gobernada y no
introducir un provider directo ni reenvíos ambiguos. Crear mini-ADR/spec antes de
implementar; no asumir que TTS es necesario para entregar el valor de BL-26.

### BL-21 · Listas TODO (múltiples listas por usuario) ✅ implementado — 2026-09-10
Permitir al usuario crear y gestionar **listas de tareas (TODO)** con nombre
personalizado (ej. "Trabajo", "Personal", "Compras", "Proyecto X").
Cada lista contiene items con: título, descripción opcional, estado
(pending/done), prioridad opcional, fecha límite opcional y orden manual.
Operaciones: crear/renombrar/eliminar lista; añadir/editar/mover/eliminar
item; marcar done/pending; reordenar (drag-and-drop lógica); listar items
con filtros (estado, prioridad, fecha). Diferencia clave con `reminders`:
no hay trigger temporal automático ni worker — es gestión activa iniciada
por el usuario. Requiere: modelos (`todo_lists`, `todo_items`), repositorio,
servicio, tools (`propose_`/`execute_` para WRITE), prompts/skill, tests
unit + integration, migración idempotente en `migrations/init.sql`.
**Prioridad:** P2 — hace el asistente "usable de verdad" para gestión diaria.
**Implementación (2026-09-10):** dominio `src/domain/todos/` (models+service),
`src/repositories/todos.py` (SQL parametrizado, user-scoped), 12 tools en
`src/agent/tools/todos.py` (listas con propose/execute + items directos),
registro en `_init_domain_tools()`, skill `prompts/skills/todos.md`,
`tablas ancora.todo_lists/todo_items` en `migrations/init.sql`,
29 unit tests + 7 integration tests nuevos (168 unit passing, Ruff limpio,
mypy limpio en archivos nuevos). El wiring FastAPI del worker se corrigió
posteriormente en BL-22/specs/012. E2E Telegram pendiente (bloqueado por BL-18).

---

### ~~BL-28 · Comandos de Telegram: manejo nativo de `/new` y namespace `/` reservado~~ ✅ implementado
`5625bbb` + `ed864fb` (2026-09-20). `domain/interactions/commands.py` resuelve
`/new` (nueva generación de conversación) y `/help`/`/start`; cualquier otro
comando válido recibe un reply constante ("no disponible") y **nunca llega al
LLM**, ni arrastra historial al proveedor. La respuesta viaja por el mismo
outbox durable que una respuesta del Agent (chunks, delivery state, ambigüedad)
mediante `claim_command_reply` (gated en `accepted` ⇒ un replay no responde dos
veces; nada externo ocurre antes del commit). La generación se guarda en la
fila del propio `/new` (`agno_session_id`) y los runs siguientes la resuelven
con `current_session_id(chat_id)`; texto que empieza por `/` pero no es comando
Telegram válido (`/home/user/x`) sigue siendo conversación. Telemetría nueva
bounded (`ancora.command` ∈ {new, help, start, unsupported}) añadida a la
allowlist con test de privacidad. Cobertura: 6 unit (parse/replies/generaciones)
+ 5 unit de processor + 4 de integración PostgreSQL (`/new` sin run, sesión
heredada por el mensaje siguiente, claim único, `current_session_id`).

**Decisión:** sin `propose/execute` — los comandos no escriben datos canónicos
ni llaman a proveedores; `/new` sólo abre una generación conversacional.

**Paso de operador (BLOQUEADO — requiere tu aprobación):** publicar el menú de
autocompletado en Telegram con
`python scripts/telegram_webhook.py commands` (usa `setMyCommands` con el mismo
mapa del dominio; sin esto `/new` funciona igual pero no aparece al escribir
`/`). No lo he ejecutado: cambia estado del bot de producción.

### ~~BL-29 · Renderizado real de Markdown en las respuestas de Telegram~~ ✅ implementado
`5625bbb` + `ed864fb` (2026-09-20). Se eligió **HTML** (no MarkdownV2) por ser
mucho más tolerante: `notifications/markup.py` escapa `&`, `<`, `>` de todo el
texto literal y emite etiquetas sólo desde una whitelist propia (`b`, `i`, `s`,
`code`, `pre`, `a` con URL `http(s)` sin comillas, headings y bullets `•`). Un
span sin cierre queda como texto literal (nunca tag roto) y un bloque de código
sin cerrar no deja `<pre>` colgando, así que un corte de chunk puede perder
formato pero jamás significado. Si el render excede 4096 chars, la entrega manda
el chunk en texto plano; y si Telegram rechaza el markup (`TelegramSendError`
ahora lleva `description`), el notifier reintenta una vez en texto plano en
lugar de perder el mensaje. El contenido persistido sigue siendo el Markdown
original del modelo (presentación ≠ auditoría). `format_reminder_message` sigue
en texto plano a propósito (ADR-003/§2.8). Cobertura: 19 unit de render + 4 unit
de notifier.

**Límite conocido:** el path AgentOS legado (admission deshabilitada) entrega con
el cliente Telegram interno de Agno y no pasa por este notifier.

### BL-30 · Tool de búsqueda web gobernada (respuestas "¿qué es X?")
Añadir una capability de consulta a Internet para términos desconocidos
("que me digas qué es X"), sin investigación profunda ni browsing largo.
Debe seguir la disciplina de capabilities: nueva tool en `src/agent/tools/`
con servicio de dominio detrás, `EXTERNAL_ACTION` por riesgo (salida del
perímetro hacia terceros → gobernanza; decidir en spec si requiere
propose/execute o se trata como READ sujeto a rate/budget), ruta de red en la
capa de infraestructura, datos devueltos = DATA no confiable, sin contenido
personal en logs/OTel, coste/uso auditables y presupuesto del run aplicado
(hooks de budget ya existentes la cortan igual que cualquier tool).

**Fase 1 implementada localmente (2026-10-04, specs/025):** Tavily directo tras
un puerto de dominio, habilitación explícita (`WEB_SEARCH_ENABLED=false` por
defecto), consulta pública minimizada, `basic`, máximo 5 resultados, sin
`include_answer` ni contenido bruto, caché sólo en memoria y envoltorio
`untrusted_data`. No persiste consultas/resultados y rechaza patrones básicos de
datos personales/sensibles. La Fase 2 (spike OpenRouter/LiteLLM) queda diferida
y documentada en `specs/025-web-search/spec.md`.

**Opciones a evaluar en el spec:** API de búsqueda (Brave/Serper/Tavily…) con
clave por secretos + síntesis por el propio modelo, o un modelo con búsqueda
nativa vía OpenRouter si existe y permite el Gateway. El resultado debe incluir
fuentes/URLs y fecha de consulta suficientes para distinguir conocimiento del
modelo de información recuperada; no presentar snippets como hechos verificados.
Aplicar allow/deny de destinos, protección SSRF si se recuperan páginas, timeout,
máximo de resultados/páginas/bytes, cache con TTL, rate limit y budget por run.
No enviar memoria personal ni contexto conversacional completo al buscador: sólo
la consulta mínima necesaria, advertir/confirmar antes de incluir datos sensibles
y registrar metadata de proveedor/coste sin query ni contenido. **Prioridad P2**
(valor alto de UX, no bloquea MVP). Al añadir capability: seguir
`docs/adding-tools.md` + skill prompt + tests/evals de prompt injection web.

### BL-31 · Deduplicación de documentos por hash de contenido
Comprobado que no existe: `storage_key` es UUID aleatorio (local y Supabase) y
`ancora.documents` no guarda hash — el mismo fichero enviado dos veces se
almacena, procesa y cobra dos veces. Propuesta: columnas `content_sha256
CHAR(64)` + índice `(user_id, content_sha256)` en `documents` (migración
Alembic aditiva + `init.sql`); calcular SHA-256 en `DocumentService.ingest`
antes de almacenar; si existe fila vigente del mismo usuario, reutilizar el
registro existente (no re-almacenar bytes) y decidir política de extracción:
re-usar la extracción previa y devolver su resumen (recomendado — evita coste
duplicado) con opción de re-extraer explícita. Mantener el original_filename
de la última subida si se desea, sin borrar documentos previos (provenance).
El hash es derivado del contenido, no dato sensible; auditar en
`ai_extractions` el `document_id` real usado. **Prioridad P2** (ahorro directo
de coste y ruido canónico; encaja antes del E2E de visión/PDF).

### BL-32 · Acuse de recibo temprano para procesos pesados (fast-ack UX)
Cuando la respuesta previsible tarde (documento/imagen/PDF), enviar en el
mismo run un mensaje inmediato tipo "📄 Documento recibido, analizando…" antes
de la inferencia, sin romper las garantías de specs/013. Restricciones: no
reenvíos ambiguos (el acuse es un mensaje más de la outbox con su delivery
state; si falla se marca y no se reintenta a ciegas), no duplicar acuses si el
update se reprocesa (idempotente por `interaction_id`), y el mensaje final
sigue siendo único. Alternativas a evaluar: (a) acuse como chunk previo de la
misma `logical_response`; (b) mensaje efímero borrado al responder (ensucia y
necesita `deleteMessage`); (c) solo `typing` continuo (ya existe como BL-17,
no basta para 15–30 s de visión). Propongo (a) con heuristic gate: media/flags
por tipo de interacción (media ⇒ acuse; texto ⇒ no).

Generalizar el mecanismo como **eventos internos tipados de progreso**
metadata-only (`operation_started`, `stage_changed`, `operation_succeeded`,
`operation_failed`), vinculados a `interaction_id`/`correlation_id`. Productores
como documentos, STT, búsqueda web o consolidación de memoria publican estados
semánticos, no texto de canal; un proyector Telegram decide qué eventos merecen
mensaje y los persiste primero en la outbox. Los hooks son puntos de extensión
internos, explícitos y acotados del lifecycle —no plugins dinámicos—, con timeout,
aislamiento de errores y allowlist de payload. No pueden alterar identidad,
autorización, argumentos/resultados de tools ni convertir un fallo de delivery en
repetición del Agent. **Prioridad P3** (pulir después del E2E de visión, donde la
latencia real será medible).

### BL-35 · Ingesta gobernada de documentos ofimáticos (DOCX/XLSX/PPTX)
Ampliar Document Memory para recibir formatos ofimáticos habituales sin ejecutar
macros, relaciones externas, objetos embebidos ni contenido activo. Implementar
extractores deterministas detrás de un puerto de infraestructura: texto y tablas
de DOCX, hojas/celdas relevantes de XLSX y texto/notas de PPTX; después reutilizar
el pipeline de almacenamiento, extracción gobernada, provenance y propuestas
existente. El contenido extraído sigue siendo DATA, nunca instrucciones.

**Dependencia obligatoria:** BL-31 debe estar cerrado antes de activar esta
capability para evitar almacenamiento y coste duplicados. Aplicar allowlist real
por firma/MIME además de extensión, límites de bytes, entradas ZIP, ratio de
compresión, profundidad, nº de hojas/diapositivas/filas/celdas, texto total y
tiempo; rechazar cifrado/contraseña, macros y formatos legacy binarios inicialmente.
No renderizar fórmulas ni seguir hyperlinks/conexiones externas. Conservar original
y provenance, y declarar extracción parcial/truncada al usuario. **Prioridad P2.**
**Criterio de cierre:** fixtures benignas y maliciosas (ZIP bomb, path traversal,
macro, archivo renombrado y workbook desmesurado), deduplicación, aislamiento por
usuario y E2E Telegram por cada formato soportado.

### BL-38 · Conversión de documentos texto↔Markdown/PDF reutilizando lógica de `mcp_doc_to_markdown` 🔶 en curso — specs/021
Existe un servidor MCP externo (`C:\Users\0020572\OneDrive - ViewNext\IA\Research\tools\mcp_doc_to_markdown.py`,
fuera de este repositorio) con conversores ya probados: PDF con capa de texto y
DOCX → Markdown (`pymupdf4llm`, `mammoth`/`markdownify` vía `docx_to_md_app.py`),
PDF escaneado → Markdown por visión página a página (`pdf_img_to_md.py`,
reutilizable como adaptador `DocumentExtractionPort` — mismo patrón que T9/BL-6),
detección de PDF escaneado vs. texto (`get_pdf_info`, basado en
`page.get_text("text")` con PyMuPDF), VTT → Markdown y **Markdown → DOCX**
(`markdown_docx_converter.py`).

**No se conecta ese servidor MCP como infraestructura del runtime** (viola
AGENTS.md §2.1/§2.9: no es un provider gobernado, no pasa por `LLMAccess`, no
tiene `RuntimeConfigSnapshot`/budget/auditoría y vive fuera del repo). Lo que se
incorpora es la **lógica determinista de conversión** portada a
`src/domain/documents/` detrás de un puerto de infraestructura, siguiendo el
mismo patrón que `DocumentExtractionPort`:

1. **Selección de ruta de extracción por capa de texto.** Antes de invocar la
   ruta visual (`ancoramind-vision`, BL-6), comprobar con PyMuPDF si el PDF tiene
   texto extraíble (equivalente a `get_pdf_info`/`likely_scanned`). Si lo tiene,
   extraer con `pymupdf4llm` (determinista, sin coste de inferencia ni budget);
   si no, seguir la ruta visual ya implementada. Esto es exactamente el
   refinamiento ya anotado en BL-6 ("detectar capa de texto para preferir
   extracción textual… reservar visión para escaneados") y cierra ese pendiente.
2. **Extracción DOCX determinista** como parte de BL-35 (ingesta ofimática):
   reutilizar el enfoque de `docx_to_md_app.py` (texto + tablas a Markdown, modo
   `remove`/`save` para imágenes) detrás del mismo puerto, con los límites de
   seguridad ya exigidos en BL-35 (sin macros, sin relaciones externas, límites
   de tamaño/profundidad).
3. **Markdown → PDF para compartir salidas del asistente.** Hoy AncoraMind sólo
   entrega texto/HTML por Telegram (BL-29). Añadir una capability
   `propose_export_document` / `execute_export_document` (o, si se decide READ
   por ser generación efímera sin escritura canónica, justificarlo explícitamente
   en el spec) que convierta un Markdown (nota, resumen, lista TODO exportada,
   etc.) a PDF y lo entregue como documento adjunto de Telegram
   (`sendDocument`). El repo de origen no incluye un conversor Markdown→PDF
   (sólo Markdown→DOCX); evaluar en el spec una librería determinista sin
   dependencias de sistema pesadas (p. ej. generar DOCX con
   `markdown_docx_converter.py` y convertir a PDF, o un renderer HTML→PDF
   embebible) y documentar la decisión con sus límites de tamaño/tiempo.
4. **VTT → Markdown** como adaptador adicional de `DocumentExtractionPort` si
   aparece un caso de uso real (transcripciones de reuniones); no implementar
   especulativamente sin ese caso.

**Restricciones de gobernanza a preservar:** el contenido de cualquier documento
convertido sigue siendo DATA, nunca instrucciones (AGENTS.md §2.8); la
inferencia de la ruta visual sigue pasando por `LLMAccess`/Gateway con
`RuntimeConfigSnapshot`, budget y auditoría (no se copia `create_vision_llm_client`
tal cual — ese cliente físico directo del script de origen debe sustituirse por
el adaptador `DocumentExtractionPort` ya existente); ninguna conversión ejecuta
macros ni sigue referencias externas; los límites de tamaño/páginas/tiempo ya
vigentes para documentos (BL-6/BL-35) aplican igual aquí. Dependencias de Python
nuevas (`pymupdf4llm`, `mammoth`, `markdownify`, `python-docx`) se añaden a
`pyproject.toml` sólo tras confirmar licencia y huella de instalación.

**Prioridad P2.** El punto 1 (detección de capa de texto) es de bajo esfuerzo y
ahorro directo de coste — candidato a adelantarse dentro del benchmark de BL-6.
Los puntos 2 y 3 dependen de BL-35 y BL-29 respectivamente y deben spec-earse
junto a ellos, no de forma aislada. **Criterio de cierre:** PDF de texto usa la
ruta determinista (cero coste de inferencia) y PDF escaneado sigue usando
visión; export Markdown→PDF probado con al menos una nota/lista real y entregado
por Telegram con evidencia en `verification.md`; ningún adaptador nuevo crea un
provider físico ni bypassa `LLMAccess`.

**Actualización 2026-09-29 (specs/021 creado):** SDD redactado con tres fases.
Fase 1 (detección de capa de texto + extracción determinista de PDF con
`pymupdf4llm`) es autocontenida y lista para implementar — resuelve el
refinamiento pendiente de BL-6. Fase 2 (DOCX determinista) queda bloqueada por
el cierre de BL-35. Fase 3 (export Markdown→PDF) queda bloqueada por una
decisión de diseño propia (DOCX→PDF vs. HTML→PDF) y por BL-29. Ver
`specs/021-document-conversion-toolkit/`.

**Fase 1 implementada localmente (2026-10-03):** `extract_pdf_text_markdown`
(`src/agent/document_vision.py`, PyMuPDF + `pymupdf4llm.to_markdown`, mismo
límite `document_vision_max_pdf_pages` que la ruta visual — sin introducir un
tope independiente) se cablea en `analyze_document`
(`src/agent/tools/documents.py`): un PDF con `has_extractable_text` ya usa la
ruta determinista y nunca llama a la ruta visual; `DocumentService.ingest`
acepta `extracted_text` y lo trata como el `text_preview` ya existente para
`text/*` (mismo acotado `MAX_TEXT_PREVIEW_BYTES`, mismo tratamiento como DATA
no confiable). Señal metadata-only (`ancora.document.extraction_route` ∈
{`deterministic`, `visual`, `none`}) añadida al allowlist de
`src/observability/telemetry.py` y emitida en `DocumentService._extract`
(T7). `pymupdf4llm>=1.24.0,<2.0.0` añadido a `pyproject.toml` (mismo régimen
de licencia que `PyMuPDF`, ya aceptado). 9 tests nuevos (693 unit passing),
Ruff/mypy limpios. **Pendiente:** T8/T9 de `specs/021/tasks.md` marcados
hechos; falta validar con un PDF real de usuario vía Telegram (bloqueado por
las restricciones de infraestructura actuales) antes de cerrar el criterio de
cierre completo de la fase.

### BL-13 · Memoria personal y consolidación gobernada «Dream»
Convertir la "Soft Personal memory" de `docs/architecture.md` §7 en una capacidad
propia de AncoraMind para aprender preferencias estables, hábitos útiles y estilo
de interacción (idioma, longitud/tono, formatos, nombres/apodos frecuentes), sin
confundirlos con datos canónicos ni con el resumen de contexto de BL-34.

Un proceso incremental «Dream» revisa únicamente interacciones ya finalizadas
desde un cursor durable, en lotes acotados, y produce **candidatos estructurados**
con categoría, valor, confianza, evidencia/provenance, vigencia y posible conflicto.
La inferencia pasa por `LLMAccess`, ruta lógica versionada, snapshot, budget, ledger
de uso y telemetría metadata-only. El prompt vive en `prompts/`; historial,
documentos y resultados de tools son DATA no confiable. Dream no puede editar
prompts, `SOUL`, skills, archivos, permisos ni memoria canónica, ni crear nuevas
capabilities. Un hook tipado post-interacción puede marcar trabajo pendiente, pero
la consolidación se ejecuta fuera del request y nunca retrasa ni reejecuta la
respuesta Telegram.

**Política de promoción:** preferencias explícitas del usuario pueden activarse
con alta confianza y auditoría; inferencias implícitas requieren repetición/evidencia
suficiente o confirmación humana según sensibilidad. Correcciones explícitas
reemplazan la versión anterior sin borrar provenance. Hechos sensibles, secretos,
credenciales, instrucciones operativas, datos de terceros y estados pasajeros no
se aprenden automáticamente. La memoria canónica siempre prevalece ante conflicto.
El usuario debe poder consultar «qué sabes/prefieres sobre mí», corregir, olvidar,
desactivar el aprendizaje y solicitar purga; estas mutaciones siguen gobernanza y
quedan auditadas.

Decidir en spec/ADR el almacenamiento: se recomienda modelo de dominio/repository
propio en schema `ancora` para no atar el producto a Agno, con cifrado/retención y
aislamiento por usuario, enmendando `docs/architecture.md` §7 si se aprueba. Evitar
un blob opaco único: usar registros versionados y estados
`candidate/active/rejected/superseded/deleted`. **Prioridad P2**, después del cierre
operativo de BL-23; puede desarrollarse en paralelo a BL-34 una vez fijados sus
contratos. **Criterio de cierre:** evals de preferencia explícita, repetición,
contradicción/corrección, prompt injection, dato sensible, borrado y precedencia de
memoria canónica; E2E que demuestre personalización posterior sin filtrar contenido.

### BL-36 · API de aplicación multicanal para clientes web/backend
Exponer las capacidades conversacionales y operativas de AncoraMind mediante una
API HTTP versionada, para que una página web, aplicación móvil o pequeño backend
(BFF) pueda ofrecer los mismos casos de uso disponibles desde Telegram sin
duplicar lógica de negocio. No es un endpoint directo al modelo, a las tools o a
los repositorios, ni una API compatible con OpenAI: es la API del producto y debe
atravesar la misma admisión, identidad confiable, `GovernedInteractionRunner`,
`LLMAccess`, budgets, propuestas/confirmaciones, auditoría y aislamiento por
usuario que cualquier otro canal.

**Contrato inicial recomendado:**

- `POST /api/v1/interactions` acepta texto, `session_id` opcional y referencias a
  adjuntos ya subidos; requiere `Idempotency-Key` y devuelve `202` con
  `interaction_id`, `correlation_id` y estado, sin mantener una petición HTTP
  abierta durante toda la inferencia.
- `GET /api/v1/interactions/{id}` devuelve estado, progreso metadata-safe y la
  respuesta final sólo al propietario; polling es suficiente para v1. WebSocket o
  SSE queda como optimización posterior basada en eventos/outbox de BL-32, nunca
  como streaming directo de tokens sin persistencia.
- Endpoints autenticados para subir/consultar documentos y para consultar,
  confirmar o rechazar `ActionProposal` reutilizan servicios existentes; no crean
  rutas mutantes paralelas que eviten `propose_* → execute_*`.
- Las sesiones son identificadores opacos scoped por usuario/canal. Una cuenta web
  puede vincularse a la misma identidad AncoraMind que Telegram sólo mediante un
  proceso explícito y auditable; nunca por nombre, email o heurística del LLM.

Crear una admisión **agnóstica de canal** y un modelo de interacción común en el
Core (`channel`, `external_interaction_id`, principal/user, payload cifrado,
idempotency key, estado y deliveries), conservando un adaptador Telegram y un
adaptador HTTP. La migración debe preservar la semántica actual
`same source + external interaction/idempotency key => at most one Agent execution`
y los estados `accepted → agent_started → terminal`; después de `agent_started`
no hay replay automático. El runner debe recibir metadata neutral de canal en vez
de exigir IDs Telegram, sin perder trazabilidad de los flujos existentes.

**Seguridad/API:** autenticación real (OIDC/session para BFF o tokens API
revocables y hasheados para integraciones), scopes/roles, rate/concurrency limits,
límites de body/adjuntos, CORS deny-by-default, CSRF cuando haya cookies, rotación
de credenciales y errores sin contenido personal. El `user_id` se deriva siempre
del principal autenticado. Definir OpenAPI, schemas cerrados, versionado y
compatibilidad; no exponer prompts, rutas físicas/modelos, secrets, argumentos
internos de tools ni trazas. Aplicar la misma retención/cifrado y política
metadata-only de specs/013.

**Despliegue recomendado:** el navegador habla con un BFF pequeño, y el BFF con
AncoraMind mediante la API; así las credenciales de servicio no llegan al cliente.
Para un frontend first-party puede usarse cookie segura/OIDC contra el mismo host,
pero la UI no forma parte de esta historia. **Prioridad P2**, después del cierre
operativo de BL-23 y coordinada con BL-24 para identidades. **Criterio de cierre:**
un cliente de referencia sin Telegram completa conversación, documento,
consulta READ y propuesta/confirmación WRITE; duplicados ejecutan el Agent como
máximo una vez; otro usuario no puede leer estado, respuesta, adjuntos ni
propuestas; tests contract/unit/integration y E2E sobre Railway.

### BL-41 · Recurrencia en calendario/recordatorios + snooze 🔶 implementado localmente — specs/024

Hoy `calendar_events` y `reminders` solo soportan ocurrencias únicas: no existe
"cada año", "cada semana" ni "cada mes", y un evento de calendario nunca
dispara un aviso de Telegram (solo lo hacen los recordatorios, totalmente
desacoplados hoy). Añadir recurrencia simple (frecuencia + intervalo + fin
opcional, sin RRULE) a ambos dominios: en calendario mediante **expansión
virtual** en lectura (`check_calendar`), sin materializar ocurrencias futuras
ni worker nuevo; en recordatorios insertando una fila `pending` nueva tras
cada disparo exitoso (manteniendo la fila `fired` como auditoría permanente),
con purga automática de `fired` con más de 90 días como housekeeping del
propio worker. `propose_calendar_event`/`execute_calendar_event` ganan
parámetros opcionales para vincular, en la misma propuesta, un recordatorio
recurrente al evento (resuelve el caso "cumpleaños que avisa cada año" en un
solo paso). Nuevo par gobernado `propose_reminder_snooze`/
  `execute_reminder_snooze` para posponer un recordatorio ya disparado (5 min–7 días),
independiente de su recurrencia. **Prioridad P2.**

**Estado:** implementado localmente — 684 unit + 94 integration tests verdes,
Ruff y `mypy src/` limpios; migración `0007_recurrence_snooze` aplicada.
Pendiente con el propietario: validación E2E real por Telegram (ver
`specs/024-recurring-events-reminders/verification.md`). **Criterio de
cierre:** ver `specs/024-recurring-events-reminders/spec.md` §Success Criteria.

## P3 — Calidad del agente

### Deuda técnica · Hardening incremental de `mypy src/` ✅ completada — specs/019

Baseline local del 2026-09-27: 93 errores en 14 archivos bajo el modo estricto
actual. El trabajo se hace por grupos cohesivos sin relajar configuración ni
silenciar errores. Resultado: `mypy src/` limpio en 105 módulos; se corrigieron
`GovernedInteractionRunner`, repositorios SQLAlchemy y helpers de tools. Ver
`specs/019-mypy-hardening/`.

### Calidad estática · `mypy src/` como gate CI ✅ completada — specs/020

Con aprobación explícita, el job `quality` ejecuta `mypy src/` después de Ruff y
antes de los tests unitarios. El alcance mantiene 105 módulos de `src/` con modo
estricto; no incluye tests, scripts ni migraciones. La primera ejecución verde de
GitHub Actions fue confirmada el 2026-09-27.

### BL-34 · Política de contexto por tokens y compactación gobernada
La mitigación actual (`num_history_runs=10`, `add_history_to_context=True`) acota
turnos, pero no el tamaño real: diez respuestas largas pueden agotar modelos
pequeños y desperdiciar ventana en modelos grandes. Sustituir el número fijo como
protección principal por una política calculada desde la ventana efectiva de la
ruta/modelo y el budget del run, reservando espacio explícito para instrucciones,
mensaje actual, schemas/tools, respuesta y margen de seguridad.

Cuando el historial no quepa, conservar mensajes recientes y generar un checkpoint
compactado de lo anterior mediante una ruta lógica gobernada. El checkpoint debe
ser reemplazable, versionado, acotado y enlazado al rango de mensajes que resume;
no es memoria personal ni canónica y no puede introducir permisos, hechos no
presentes o instrucciones provenientes de contenido no confiable. Si la
compactación falla o excede budget, degradar de forma determinista a truncado
seguro sin reintentos genéricos. Separar esta **memoria de trabajo** de BL-13:
BL-34 mantiene continuidad de la conversación; BL-13 aprende preferencias
duraderas con provenance y reglas distintas.

Configurar umbrales por revisión de runtime, medir tokens estimados/reales y emitir
eventos tipados metadata-only compatibles con BL-32. Definir además retención y
purga de sesiones en `agno_runtime`. **Criterio de cierre:** tests con historiales
largos, mensajes/tool calls grandes, cambio de modelo/ruta, compactación fallida y
ausencia de contenido personal en logs/OTel.

### BL-37 · Cerrar gates de calidad detectados en auditoría técnica (2026-09-27)
Auditoría de arquitectura/consistencia sobre `main.py`, `ancora_agent.py`,
`governed_model.py`, `governed_agent_factory.py`,
`governed_interaction_runner.py`, tools de `todos`/`notes`/`maintenance`/
`calendar`/`reminders`/`vehicles`, `repositories/actions.py`,
`domain/llm_access/`, `storage/`, `domain/interactions/commands.py` y
`notifications/markup.py`: no se detectó drift arquitectónico respecto a
AGENTS.md §2 ni a los ADRs vigentes. Dos gaps de configuración de gates quedan
pendientes de decisión de prioridad (no aplicados directamente por ser cambios
de policy transversal, no fixes puntuales de código):

- **Ruff sin reglas de docstrings** (`D`) ni de seguridad (`S`) en
  `pyproject.toml` `[tool.ruff.lint]`, pese a que el docstring de cada tool en
  `src/agent/tools/` es el contrato/schema que ve el LLM (AGENTS.md §4).
  Evaluar activar `D` al menos sobre `src/agent/tools/` vía `per-file-ignores`
  inverso, y `S` sobre todo `src/` si el ruido de falsos positivos es
  manejable.
- **`pytest-cov` instalado sin `--cov-fail-under`** en
  `[tool.pytest.ini_options]`: la cobertura se mide pero no es un gate real de
  CI. Fijar un umbral y añadirlo al pipeline una vez medida la cobertura base
  actual.

Los hallazgos de menor severidad (mensajes de error genéricos sin distinguir
payload inválido de fallo de infraestructura en `calendar.py`, `reminders.py`
y `maintenance.py`) se corrigieron directamente en la misma fecha: se añadió
`except (KeyError, TypeError, ValueError)` antes del `except Exception`
genérico, siguiendo el patrón ya existente en `vehicles.py`/`todos.py`.
**Criterio de cierre:** decidir y, si se aprueba, aplicar `D`/`S` con
`ruff check` limpio, y `--cov-fail-under` con `pytest tests/unit/` en verde.

### BL-8 · Evals agentic 🔶 en curso — specs/014 + 018
Base determinista implementada: contrato JSON v1, runner local sin llamadas a
LLM/tools/servicios y 19 casos sintéticos actuales para `confirmation`,
`documents`, `response_style`, `security`, `tool_selection` y `vehicle` (15 en la
entrega inicial). El runner valida schema, cobertura, expectativas
contradictorias y ausencia de secretos obvios; ejecutar
`python scripts/run_evals.py` tras cambios de prompts/models/tools.

**Actualización 2026-09-27 (specs/018):** `src.agent.evals` materializa los
catálogos ya validados en casos tipados, inyecta un executor aislado y compara
determinísticamente outcome, tool requerida/vetada y confirmación. El reporte
proyecta sólo metadata; input, contexto y respuesta permanecen en memoria. No
crea Agent, provider, `LLMAccess`, sesión de DB ni tools de producción.

**Actualización 2026-10-03 (specs/018 T6):** adaptador físico implementado
localmente — `GovernedPhysicalEvalExecutor`
(`src/agent/eval_physical_executor.py`) ejecuta un Agent real por caso,
modelo resuelto vía `LLMAccess` inyectado (nunca un provider directo),
`RuntimeConfigSnapshot`/budget propios de evaluación (bootstrap, sin
PostgreSQL) y un catálogo de 15 tools simuladas sin I/O
(`src/agent/eval_tools.py`, sin importar `src.repositories`/`src.storage`/
tools de producción). Probado solo con un `Model` scripted en memoria — sin
credenciales, sin red, sin coste (`tests/unit/test_eval_tools.py` +
`tests/unit/test_eval_physical_executor.py`, 705 unit tests en total).
`outcome` se deriva únicamente de las tools realmente invocadas; un sentinel
`no_tool_call` sustituye a `clarify`/`safe_response` cuando no se invoca
ninguna (distinguirlos exige juzgar el texto de respuesta — eso es T8, no
T6). Detalle en `specs/018-agentic-evals-execution-harness/verification.md`.

**Pendiente:** T7 — ejecutar la modalidad LLM real contra el adaptador físico
ya construido, con credenciales y presupuesto explícitamente aprobados,
fuera de CI por defecto (bloqueado por decisión de coste del propietario, no
por código). T8 — acordar scoring semántico y baseline por ruta lógica con
etiquetas humanas (bloqueado por etiquetado manual del propietario). No
almacenar contenido personal en datasets, outputs ni telemetría.

**Propuesta para el siguiente incremento (2026-09-26; no implementada):** probar
Jev como juez semántico *opcional* de los casos sintéticos de `response_style`,
después de ejecutar el Agent gobernado y comprobar por código tools, resultados
observables y confirmaciones. Comparar puntuaciones con etiquetas humanas y un
baseline versionado antes de adoptar umbrales o CI; Jev no autoriza acciones ni
sustituye los gates deterministas de seguridad. Ver
`specs/014-agentic-evals/jev-pilot-proposal.md` para alcance, compatibilidad
pendiente con `LLMAccess`/Gateway, presupuestos y criterios de decisión.

**Candidatos para la fase LLM (registrados 2026-09-23, análisis de
observabilidad; aún sin decisión):**

- **Agno evals nativo** (`agno.eval`: accuracy, agent-as-judge, reliability
  de tool calls/arguments, scorer, performance; suites con exit code para CI).
  Requisito de gobernanza: el evaluator model debe pasar por
  `LLMAccess`/Gateway, nunca por un provider directo. Encaja naturalmente con
  las categorías actuales (`tool_selection` ≈ reliability, `security`).
- **Langfuse self-hosted local** (6 contenedores: web + worker + Postgres +
  Redis + ClickHouse + MinIO; ~4–8 GB RAM): datasets, anotación manual y evals
  sobre trazas. En modo metadata-only aporta poco sobre Grafana; con contenido
  exigiría enmendar ADR-006 (decisión explícita del propietario). En Railway
  inviable por coste. **Registrado como candidato a evals en local.**
- **promptfoo** (CLI, YAML, asserts deterministas + LLM-as-judge,
  red-teaming orientado a la categoría `security`): sin vendor lock, apto
  para CI.
- **DeepEval** (pytest-native): encaja con la suite existente; opción si se
  quiere scoring semántico dentro de pytest.

Descartados de partida: LangSmith/Braintrust/OpenAI Evals (envían contenido a
terceros — incompatible con la policy de specs/013) y Ragas (RAG/vector search
fuera de alcance).

### BL-15 · Botones de confirmación en Telegram (HITL UX)
La interfaz Telegram de AgentOS ignora los `callback_query`: no soporta
inline keyboards nativamente (Discord sí — ver hallazgo en
`specs/006-vehicle-creation/verification.md`). Opciones: (a) extender el
webhook de AgentOS para procesar callback_query y enviar reply_markup vía
pyTelegramBotAPI (toca internals de Agno — seguir proceso ADR-001:
documentar → demostrar límite → proponer → decidir), (b) mantener
confirmación textual (estado actual, suficiente para POC), (c) reconsiderar
canal. Hallazgo proveniente del E2E de specs/006.
**Previsto para:** post-MVP, junto a la decisión de BL-14 (Supabase) si hay
migración de runtime.

### BL-16 · Retirar workaround SafeOpenRouter cuando Agno valide tool calls
El E2E de specs/006 descubrió que `minimax/minimax-m3:free` vía OpenRouter
(backend GMICloud) emitió un tool call vacío junto al válido. Agno 2.9.0 le
añadió UUID, lo persistió y OpenRouter rechazó el siguiente turno. Workaround
actual: `SafeOpenRouter` filtra calls incompletos en las rutas streaming y
no-streaming antes de ejecutar/persistir. Es acoplamiento a métodos privados
de Agno.
**Criterio de cierre:** al actualizar Agno o cambiar de modelo/proveedor,
reproducir el caso; si Agno ya filtra llamadas incompletas, eliminar subclase
y sus tests. Mientras exista, test unitario obligatorio sobre la forma exacta.

### BL-17 · Mantener indicador «escribiendo…» durante procesos largos
Agno 2.9 Telegram envía `send_chat_action("typing")` una sola vez antes de
procesar. Telegram lo expira a los pocos segundos; búsquedas/tools lentas
parecen bloqueadas. Implementar un refresco periódico mientras dure el run,
cancelándolo siempre en `finally`. Preferible a enviar/borrar un mensaje
«Procesando…», que ensucia el chat y requiere más llamadas API.
**Restricción:** Agno no expone configuración/hook para refrescarlo; aislar la
extensión en la capa `agent/` y seguir ADR-001 (no tocar domain). Añadir tests
de cancelación en éxito y error. Post-MVP salvo que la latencia empeore.

### BL-12 · Introducir Alembic como sistema de migraciones ✅ implementado — 2026-09-13
Alembic es la historia canónica del schema `ancora`: revisión
`0001_ancora_baseline` idempotente para adoptar bases preexistentes y
`0002_llm_governance` para los cambios aditivos de specs/013.
`migrations/init.sql` se mantiene equivalente a `head` para bootstrap fresh.
Verificado contra PostgreSQL Docker: instalación vacía, adopción de schema sin
versionar conservando datos, ejecución doble de `init.sql`, upgrade a head y
downgrade `-1` que retira solo specs/013. Tres integration tests nuevos; Alembic
y las revisiones se incluyen en la imagen Docker y Ruff/CI cubren `migrations/`.

### BL-14 · Migrar infraestructura a Supabase 🔶 en curso — specs/007 + ADR-002
**Decisión del propietario (2026-09-05):** trabajar con Supabase desde ya en
vez de PostgreSQL en contenedor. **Hecho (2026-09-06):** migración baseline
`ancora_baseline` aplicada (8 tablas), bucket privado `ancora-documents`
creado, `SupabaseDocumentStorage` + factory (`DOCUMENT_STORAGE_BACKEND`),
ADR-002, Storage real verificado y 26 tests nuevos (123 total). Seguridad:
`rls_auto_enable()` ya no es ejecutable por roles API y Security Advisor está
limpio. Session pooler sync/async e integración directa de repositorios ya
verificados. E2E nota y alta de vehículo PASS; fixes de foto, búsqueda de
matrícula formateada y OpenRouter streaming listos. **Pendiente/pausado:**
re-test Telegram de documento y búsqueda para cerrar T7, bloqueado hasta
resolver BL-18 (alternativa autorizada a ngrok). pgvector: disponible (0.8.2),
NO instalado — diseño solo hasta BL-6.

---

### BL-43 · Pantalla de administración centralizada 🔶 implementado localmente — specs/027

AncoraMind depende hoy de varias piezas externas (Railway, Supabase,
OpenRouter, LiteLLM Gateway, Grafana) además de dos superficies HTTP de
administración propias — `/admin/runtime-config/*` (BL-23/specs/013) y
`/admin/telegram-pairing/*` (BL-24/specs/017) — operadas sólo desde dos
scripts CLI. Se añade `GET /admin/dashboard`: una página HTML autocontenida
(sin build, sin dependencias nuevas) con cuatro paneles — invitaciones de
pairing, runtime-config (status/validar/crear revisión/activar/rollback, con
paridad completa frente al CLI), salud (`GET /health/readiness` tal cual) y
enlaces centralizados a las plataformas externas (estáticos salvo Supabase y
LiteLLM Gateway, que reutilizan el estado ya calculado por `HealthRegistry`).
Gateada por `ADMIN_DASHBOARD_TOKEN`, un secreto nuevo y propio — distinto de
`RUNTIME_CONFIG_ADMIN_TOKEN` — porque el dashboard vive en un navegador (más
expuesto que una terminal); su backend llama directamente a
`TelegramPairingService` y al `RuntimeConfigManager` ya existente, sin
reenviar peticiones HTTP a los admin API existentes. Los CLIs
(`scripts/runtime_config.py`, `scripts/telegram_pairing.py`) siguen
funcionando sin cambios; conviven con el dashboard como dos fachadas sobre el
mismo dominio.
**Criterio de cierre:** validado a mano en Railway con las variables
`ADMIN_DASHBOARD_*` configuradas (ver specs/027/verification.md y
`docs/runbooks-027-admin-dashboard.md`).

### BL-44 · Parada de emergencia manual para Agent/LLM 🔶 pendiente de diseño

Hoy sólo existe un hard-stop **automático** al 90% del gasto
(`CostGovernanceConfig.hard_stop_threshold_pct`) — nada que el propietario
pueda accionar a mano si la aplicación falla de forma general o el gasto se
dispara de otra manera no cubierta por ese umbral. Surgió al definir BL-43,
que deliberadamente lo deja fuera de alcance: construir un interruptor real
significa tocar la ruta crítica de `LLMAccess`/`GovernedModel` que specs/013
somete a su matriz de aceptación A–Y, y merece su propio spec en vez de
mezclarse con una pantalla nueva. Diseñar: una señal durable (fuera del
esquema versionado de `RuntimeConfiguration`) que `LLMAccess` compruebe antes
de cada llamada al Gateway, y un panel nuevo en el dashboard de BL-43 una vez
diseñada.

---

## Hecho (registro)

| Item | Spec | Fecha |
|---|---|---|
| M1 Agent Runtime | specs/001 | — |
| M2 Canonical Memory (notes) | specs/002 | — |
| M3 Document Memory | (sin spec — BL-9) | — |
| M4 Vehicle vertical slice | specs/004 | — |
| M5 Calendar & Reminders | specs/005 | — |
| Docs multi-shell (PowerShell/Git Bash) | — | 2026-09-05 |
| BL-9 · Spec-003 retroactiva (+ fix aislamiento test_config) | specs/003 | 2026-09-05 |
| BL-11 · docs/development.md actualizado (env vars, migraciones, multi-shell) | — | 2026-09-05 |
| BL-3 · Higiene de repo (commits pendientes, push, .env no commiteado) | — | 2026-09-05 |
| BL-4 · Tool para crear vehículos (propose/execute + normalización + E2E) | specs/006 | 2026-09-06 |
| BL-10 · Unificar factory de modelo en tools de documentos (`create_model_from_settings`, respetando `LLM_PROVIDER`/`LLM_MODEL`) | — | 2026-09-09 |
| BL-19 · Baseline Ruff limpio en `src/ tests/ scripts/` (155 avisos → 0; gate global en CI) | — | 2026-09-09 |
| BL-2 · Integration tests con PostgreSQL real (16 tests, BD dedicada `ancoramind_test`, fix jsonb asyncpg en documents.py, job CI integration) | specs/009 | 2026-09-09 |
| BL-5 · Background worker de recordatorios (asyncio in-process + TelegramNotifier outbound; worker arranca con la app — ADR-003, documentado para BL-18/Railway) | specs/010 | 2026-09-09 |
| BL-21 · Listas TODO (múltiples listas por usuario: dominio + repo + 12 tools + skill + tablas; spec redactada retroactivamente — ver specs/011/verification.md) | specs/011 | 2026-09-10 |
| BL-22 · Migrar reminder worker a FastAPI lifespan (preserva lifecycle AgentOS; auto-gates + cancelación limpia) | specs/012 | 2026-09-10 |
| BL-12 · Alembic canónico + baseline/adopción + migración specs/013 + lifecycle tests | specs/013 T2 | 2026-09-13 |
| BL-23 · Interaction ledger durable (cipher/Fernet, deliveries, claim y retención) | specs/013 T3 | 2026-09-13 |
| BL-23 · Telegram admission feature-flagged (secret, private chat, allowlist, rate/queue durable) | specs/013 T4 | 2026-09-13 |
| BL-23 · Processor/outbox Telegram (claim, recovery, chunks, delivery states y typing) | specs/013 T5 | 2026-09-13 |
| BL-25 · Script E2E nativo para PowerShell | specs/015 | 2026-09-19 |
| BL-28 · Comandos de bot deterministas (`/new`, `/help`; sin IA, outbox durable, generaciones de sesión en el ledger, `ancora.command` en la allowlist) | — (BL-28) | 2026-09-20 |
| BL-29 · Renderizado Markdown → HTML de Telegram (whitelist de tags, escaping total, fallback texto plano, retry ante rechazo de markup) | — (BL-29) | 2026-09-20 |
| Preparación del cambio de modelo por defecto GPT-5.6 Luna → GPT-6 Luna (fallback directo + candidato gobernado `ancoramind-default-r3` + pricing y runbook; rollout remoto registrado en BL-23) | specs/013 + ADR-005 | 2026-09-28 |

---

## Opciones diferidas (no comprometidas; reevaluar sólo con caso de uso y spec)

- **Control visible del run:** `/stop` con cancelación cooperativa y gobernada, y
  `/status` limitado a metadata no sensible. Requieren semántica durable ante
  `agent_started`, tools/efectos externos y deliveries ambiguas; no son un simple
  `task.cancel()` ni deben prometer rollback.
- **Interfaces/canales adicionales:** una WebUI/TUI first-party completa y
  Discord/Slack/Email/WhatsApp continúan diferidos. BL-36 sí compromete la API que
  permite construir una página web o BFF pequeño; cada UI/canal adicional deberá
  consumir esa frontera o implementar un adaptador con garantías equivalentes de
  admisión, identidad y delivery. No compartir una identidad por heurística.
- **Integraciones extensibles:** MCP, plugins dinámicos y skills instalables. Antes
  exigen catálogo firmado/allowlisted, permisos por capability, sandboxing,
  provenance y supply-chain policy. Los hooks internos tipados de BL-32/BL-13 no
  implican abrir esta superficie.
- **Automatizaciones agentic generales/cron, generación de imágenes y API
  compatible con OpenAI:** valorar como capabilities separadas sólo cuando exista
  una necesidad concreta, modelo de autorización, budget y auditoría. La API de
  producto de BL-36 no implica compatibilidad con `/v1/chat/completions` ni expone
  selección libre de modelo/tools.
- GraphRAG, vector search, microservices y event sourcing continúan «not yet».

## Decisiones explícitamente no adoptadas

- Shell o filesystem generalistas accesibles al Agent/Dream; la infraestructura
  usa puertos y operaciones específicas con allowlist.
- Streaming directo de tokens a Telegram: la entrega continúa pasando por
  respuesta lógica durable, render seguro y outbox.
- Selección/cambio de modelo por usuario: las rutas son configuración operativa
  versionada y gobernada (ADR-005), no una preferencia conversacional.
- Reintentos genéricos de Agent/tools/acciones externas: sólo políticas específicas
  que preserven idempotencia y distingan fallos seguros de efectos ambiguos.
- Subagentes o delegación general mientras una capability/tool del agente principal
  resuelva el caso; cualquier excepción requiere necesidad demostrada y ADR.
