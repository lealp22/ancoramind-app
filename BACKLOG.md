# BACKLOG — AncoraMind

> Lista viva y priorizada de trabajo pendiente. Fuente única de verdad para
> "qué queda por hacer". Los `specs/*/tasks.md` son el registro histórico de
> "qué se hizo" (no editarlos una vez completados).
>
> Convención: cuando un item pasa a "en curso", se le asigna un número de spec
> (`specs/00X-...`) y se trabaja con SDD (spec.md → tasks.md → implementación).
> Al completarse, se tacha aquí con fecha y se enlaza su spec.

Última actualización: 2026-09-05

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

Tests: 82 passing (`pytest tests/unit/`)

---

## P1 — Cerrar el MVP (validación)

### BL-1 · E2E Telegram de M3–M5
Probar en Telegram con credenciales reales: subir documento → extracción,
registrar vehículo + mantenimiento (propose/execute), crear recordatorio y
evento de calendario (propose/execute).
**Criterio de cierre:** los 5 flujos probados y documentados en el
`verification.md` del spec correspondiente.

### BL-2 · Integration tests con PostgreSQL real
`tests/integration/` está vacío. Los 82 tests actuales mockean repositorios.
Crear integration tests contra el PostgreSQL de docker-compose (arrancar en
fixture, aplicar `migrations/init.sql`, testear repos reales).
**Criterio de cierre:** `pytest tests/integration/` verde con PostgreSQL
dockerizado.

---

## P2 — Funcionalidad para "usable de verdad"

### BL-4 · Tool para crear vehículos 🔶 en curso — specs/006
Ahora los vehículos se insertan por SQL manual en los E2E. Crear par
`propose_vehicle` / `execute_vehicle` (WRITE → ActionProposal + confirmación),
siguiendo el patrón de `maintenance.py`.

### BL-5 · Background worker para recordatorios
Los recordatorios se crean con status `pending` pero nada los dispara.
Opciones: worker asyncio en `src/main.py` (simple, POC) o APScheduler/cron.
Investigar y decidir (puede merecer un mini-ADR).

### BL-6 · OCR/vision real para extracción de documentos
La extracción IA usa filename + metadata, no el contenido real de PDFs/imágenes.
Evaluar: visión del LLM (si el modelo la soporta) vs. OCR dedicado (Tesseract,
pymupdf). Riesgo: contenido no confiable → DATA, no INSTRUCTIONS (§2 AGENTS.md).

### BL-7 · Proveedor de calendario real
Implementar un `CalendarProvider` real (Google Calendar, CalDAV o similar)
tras el Protocol existente. NoopCalendarProvider queda como default para dev.

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
actual: `SafeOpenRouter._populate_assistant_message()` filtra calls incompletos
antes de ejecutar/persistir. Es acoplamiento a método privado de Agno.
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

### BL-10 · Unificar creación de modelo en tools de documentos
`agent/tools/documents.py` instancia `OpenAIChat(id="gpt-5.4-mini")` hardcoded
en lugar de reutilizar la factory `create_model()` de `ancora_agent.py`
(respeta `LLM_PROVIDER`/`LLM_MODEL` del `.env`). Cambio pequeño, un solo sitio.

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

### BL-14 · Migrar infraestructura a Supabase (decisión explícita — abre "not yet")
**Decisión del propietario (2026-09-05):** trabajar con Supabase desde ya en
vez de PostgreSQL en contenedor. Alcance:
1. **BD principal** — proyecto Supabase *main* (versión free, sin branches;
   separación de entornos se decide más adelante o con upgrade a Pro).
   Migrar `agno_database_url` (psycopg) y `ancora_database_url` (asyncpg)
   al pooler de Supabase; aplicar `migrations/init.sql`.
   ⚠️ Free tier: pausa el proyecto tras ~1 semana de inactividad.
2. **Storage de ficheros** — nueva implementación de `DocumentStorage`
   (Protocol en `src/storage/base.py`) sobre Supabase Storage, junto a la
   de filesystem local.
3. **BD vectorial (pgvector)** — ⚠️ figura en "fuera de alcance" de este
   backlog y en AGENTS.md §8; esta mención ES la decisión explícita que la
   abre. Secuenciación: solo tiene valor tras BL-6 (OCR/contenido real);
   hasta entonces queda como diseño, no implementación.
**Criterio de cierre:** app en marcha contra Supabase (BD + storage),
migraciones aplicadas, E2E de notas/documentos OK, mini-ADR documentando
la decisión (ADR-002).
**Nota:** compatible con §2.7 (separación de DBs) — Supabase es solo el
host PostgreSQL; el schema `ancora` sigue separado del runtime de Agno.

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

---

## Fuera de alcance ("not yet" — no abrir sin decisión explícita)

GraphRAG, vector search, multi-agent, WhatsApp, web frontend, microservices,
event sourcing.
