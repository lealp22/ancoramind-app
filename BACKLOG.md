# BACKLOG — AncoraMind

> Lista viva y priorizada de trabajo pendiente. Fuente única de verdad para
> "qué queda por hacer". Los `specs/*/tasks.md` son el registro histórico de
> "qué se hizo" (no editarlos una vez completados).
>
> Convención: cuando un item pasa a "en curso", se le asigna un número de spec
> (`specs/00X-...`) y se trabaja con SDD (spec.md → tasks.md → implementación).
> Al completarse, se tacha aquí con fecha y se enlaza su spec.

Última actualización: 2026-09-19

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
| BL-23 Governed LLM Access, Telegram admission y OTel | 🔶 T2–T14 implementados; fase 6 (cambio de modelo en caliente) validada en Railway (2026-09-19); pendiente verificar matriz A–Y completa (caída Gateway/circuit, Collector/Grafana, benchmark con clave real, reconciliación de costes, rotación) — specs/013 |
| MVP usable | 🔶 E2E parcial (M1–M2 probado; M3–M5 pendiente — ver BL-1) |

Tests: 374 unit + 60 integration passing — Ruff limpio en
`src/ tests/ scripts/ migrations/`

---

## P0 — Hardening transversal de ejecución e inferencia

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

**Estado (2026-09-13):** T2 aporta Alembic y el schema reproducible. T3 aporta el
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

**Criterio de cierre:** matriz A–Y de specs/013 verificada: un mismo update
ejecuta el Agent como máximo una vez, el modelo cambia sin redeploy, ningún run
supera su budget, LiteLLM falla cerrado, la interacción es trazable por
`correlation_id` y no se exporta contenido personal.

### BL-24 · Onboarding de usuarios Telegram mediante invitaciones gobernadas
`ALLOWED_TELEGRAM_USER_IDS` permite una allowlist técnica, pero no es un proceso
práctico de alta para un grupo de evaluadores aún no definido: no se debe abrir
el bot a cualquier usuario ni pedir a cada persona que averigüe su Telegram ID.

Diseñar e implementar un flujo de invitación administrable: un operador crea una
invitación/código de alta de duración y uso limitados; la persona lo canjea en un
chat privado con el bot; el backend vincula el `telegram_user_id` observado en el
update autenticado a una identidad/autorización durable. El código es una
credencial de onboarding, no un sustituto de los controles existentes de secret
de webhook, private-chat, rate limiting, idempotencia ni auditoría de BL-23.

Decidir en el spec el canal de emisión/solicitud (web mínima, herramienta/admin
CLI u otro mecanismo), el modelo de roles/grupos, revocación, expiración,
rotación y recuperación ante canje duplicado. Secretos/códigos deben almacenarse
con hash; las operaciones administrativas y toda mutación de autorización deben
ser auditables. Mantener fail-closed: un usuario sin autorización vigente no
llega al Agent.

**Prioridad P0:** desbloquea pruebas controladas con múltiples personas y debe
integrarse con la admission durable de `specs/013`, no mediante un bypass de la
allowlist actual.

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

### BL-18 · Sustituir ngrok por Railway 🔶 en curso — specs/008
La alerta de tráfico tipo C2 hace no recomendable seguir usando ngrok en esta
red sin autorización. **Decisión (2026-09-08): Railway** como despliegue
gestionado conectado a GitHub; Supabase permanece como PostgreSQL y Storage.
Hecho: runtime compatible con `PORT`, Dockerfile, healthcheck, `railway.json`,
CI GitHub Actions, helper de webhook seguro y documentación. Pendiente: crear
servicio Railway, cargar variables, activar Auto Deploy + Wait for CI, generar
dominio, registrar webhook y repetir E2E Telegram.
**Nota (2026-09-09):** al desplegar se activará también el worker de
recordatorios (BL-5 / ADR-003 / specs/010): variables `REMINDER_WORKER_*`
opcionales (defaults válidos); su entrega es **outbound** y funciona desde el
primer deployment saludable, sin esperar al registro del webhook. Ver
`docs/deployment-railway.md` §8.
**Criterio de cierre:** dominio HTTPS Railway estable, CI/CD operativo y E2E
Telegram ejecutado sin alertas ni túneles desde el equipo local.

### BL-25 · Script E2E nativo para PowerShell
Crear `scripts/run-e2e.ps1` con paridad funcional respecto a
`scripts/run-e2e.sh`, para entornos Windows sin Bash. Debe admitir los modos
equivalentes `-Check` y `-Reset`, cargar `.env` sin ejecutar contenido como
código, validar provider/almacenamiento/base de datos, detectar Supabase frente
a PostgreSQL local, arrancar y esperar PostgreSQL local, aplicar el bootstrap
cuando proceda, iniciar/detectar ngrok, registrar el webhook de Telegram y
lanzar `python -m src.main`.

Documentar el uso desde PowerShell y cubrir al menos los caminos de validación
sin efectos externos. No duplicar ni desalinear la política de configuración:
si se extrae lógica común, mantener los dos wrappers como consumidores de la
misma fuente de verdad.

**Prioridad P1:** elimina una dependencia innecesaria de Bash para validación
E2E local en Windows.

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

---

## P2 — Funcionalidad para "usable de verdad"

### BL-6 · OCR/vision real para extracción de documentos
La extracción IA usa filename + metadata, no el contenido real de PDFs/imágenes.
Evaluar: visión del LLM (si el modelo la soporta) vs. OCR dedicado (Tesseract,
pymupdf). Riesgo: contenido no confiable → DATA, no INSTRUCTIONS (§2 AGENTS.md).

### BL-7 · Proveedor de calendario real
Implementar un `CalendarProvider` real (Google Calendar, CalDAV o similar)
tras el Protocol existente. NoopCalendarProvider queda como default para dev.

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

## P3 — Calidad del agente

### BL-8 · Evals agentic 🔶 en curso — specs/014
Base determinista implementada: contrato JSON v1, runner local sin llamadas a
LLM/tools/servicios y 15 casos sintéticos iniciales para `confirmation`,
`documents`, `security`, `tool_selection` y `vehicle`. El runner valida schema,
cobertura, expectativas contradictorias y ausencia de secretos obvios; ejecutar
`python scripts/run_evals.py` tras cambios de prompts/models/tools.

**Pendiente:** adaptar el catálogo para ejecutar un Agent gobernado y evaluar
metadata permitida (tool/decisión/resultado), acordar scoring semántico y baseline
por ruta lógica, y añadir la modalidad LLM al flujo CI/E2E con budget explícito.
No almacenar contenido personal en datasets, outputs ni telemetría.

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

### BL-13 · Diseño Soft Personal memory (mini-ADR)
La "memoria soft personal" (preferencias, personalización) está definida en
`docs/architecture.md` §7 como "Agno (futuro) — Memory de Agno" pero no tiene
ni diseño, ni spec, ni implementación. Mini-ADR que decida: qué persiste
(idioma, formatos, apodos frecuentes...), dónde (Memory de Agno en
`agno_database_url` — respetando separación de DBs §2.7) y cómo la consumen
las tools.
**Previsto para:** post-MVP (primero cerrar BL-1). No bloquea nada actual.

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

---

## Fuera de alcance ("not yet" — no abrir sin decisión explícita)

GraphRAG, vector search, multi-agent, WhatsApp, web frontend, microservices,
event sourcing.
