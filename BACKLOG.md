# BACKLOG — AncoraMind

> Lista viva y priorizada de trabajo pendiente. Fuente única de verdad para
> "qué queda por hacer". Los `specs/*/tasks.md` son el registro histórico de
> "qué se hizo" (no editarlos una vez completados).
>
> Convención: cuando un item pasa a "en curso", se le asigna un número de spec
> (`specs/00X-...`) y se trabaja con SDD (spec.md → tasks.md → implementación).
> Al completarse, se tacha aquí con fecha y se enlaza su spec.

Última actualización: 2026-09-13

---

## Estado actual (snapshot)

| Milestone | Estado |
|---|---|
| M1 Agent Runtime (Telegram+Agno+session) | ✅ |
| M2 Canonical Memory (notes) | ✅ |
| M3 Document Memory (storage+extraction) | ✅ (specs/003 documentada retroactivamente) |
| M4 Vehicle vertical slice | ✅ |
| M5 Calendar & Reminders | ✅ |
| MVP usable | 🔶 E2E parcial (M1–M2 probado; M3–M5 pendiente — ver BL-1) |

Tests: 186 unit passing; integration requiere PostgreSQL/Docker — Ruff limpio
en `src/ tests/ scripts/`

---

## P0 — Hardening transversal de ejecución e inferencia

### BL-23 · Governed LLM Access, Telegram Admission and Observability 🔶 diseño aprobado — specs/013 + ADR-004/005/006

Convertir el acceso a LLM y la entrada Telegram en capabilities gobernadas:

```text
Telegram → admission/idempotency → Agno → logical route
→ LiteLLM Proxy → OpenRouter → provider/model
```

Incluye idempotencia durable por `update_id`, semántica at-most-once del Agent,
private-chat/allowlist reales, rate/concurrency limits, execution budget,
configuración runtime versionada y cacheada, rutas lógicas, LiteLLM privado y
fail closed, coste/circuit breaker, y OpenTelemetry Collector + Grafana Cloud.
La telemetría de producto de Agno se desactivará al activar la observabilidad
propia. Defaults aprobados: 120 s, 6 model calls, 12 tool calls como hard safety
ceiling, 8 requests Gateway y concurrencia global 2.

**Estado (2026-09-13):** diseño aprobado; implementación no iniciada. El runtime
actual sigue usando el webhook Telegram de AgentOS, provider/model de environment
y OpenRouter directo. Ver `specs/013-llm-access-governance/`.

**Criterio de cierre:** matriz A–Y de specs/013 verificada: un mismo update
ejecuta el Agent como máximo una vez, el modelo cambia sin redeploy, ningún run
supera su budget, LiteLLM falla cerrado, la interacción es trazable por
`correlation_id` y no se exporta contenido personal.

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

### BL-8 · Evals agentic
Las 5 carpetas de `evals/` están vacías: `confirmation`, `documents`,
`security`, `tool_selection`, `vehicle`. Definir formato de casos + criterios
de éxito por categoría y ejecutar tras cada cambio de prompts/models/tools
(requisito de gobernanza — ver `docs/governance.md`).

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

### BL-12 · Introducir Alembic como sistema de migraciones
`migrations/init.sql` cubre el POC (idempotente, `IF NOT EXISTS`), pero no
permite modificar tablas existentes con datos (añadir columna, cambiar tipo,
backfills). Alembic ya está en `pyproject.toml` como dependencia (`>=1.13.0`).
Baseline: registrar `init.sql` como la migración inicial (revision) y desde
ahí solo migraciones incrementales.
**Criterio de cierre:** `alembic upgrade head` ejecuta el schema completo en
una BD vacía; `alembic downgrade -1` deshace correctamente la última migración;
`migrations/init.sql` sigue para despliegues fresh sin Alembic (opcional).
**Previsto para:** antes del primer feature que modifique el schema sobre
datos existentes (BL-4, BL-6 o BL-7).

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

---

## Fuera de alcance ("not yet" — no abrir sin decisión explícita)

GraphRAG, vector search, multi-agent, WhatsApp, web frontend, microservices,
event sourcing.
