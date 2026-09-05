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
| M3 Document Memory (storage+extraction) | ✅ (spec-003 no documentada — ver BL-9) |
| M4 Vehicle vertical slice | ✅ |
| M5 Calendar & Reminders | ✅ |
| MVP usable | 🔶 E2E parcial (M1–M2 probado; M3–M5 pendiente — ver BL-1) |

Tests: 68 passing (`pytest tests/unit/`)

---

## P1 — Cerrar el MVP (validación)

### BL-1 · E2E Telegram de M3–M5
Probar en Telegram con credenciales reales: subir documento → extracción,
registrar vehículo + mantenimiento (propose/execute), crear recordatorio y
evento de calendario (propose/execute).
**Criterio de cierre:** los 5 flujos probados y documentados en el
`verification.md` del spec correspondiente.

### BL-2 · Integration tests con PostgreSQL real
`tests/integration/` está vacío. Los 68 tests actuales mockean repositorios.
Crear integration tests contra el PostgreSQL de docker-compose (arrancar en
fixture, aplicar `migrations/init.sql`, testear repos reales).
**Criterio de cierre:** `pytest tests/integration/` verde con PostgreSQL
dockerizado.

### BL-3 · Higiene de repo (inmediato)
- Commitear: `README.md` (modificado), `AGENTS.md` y `docs/quick-start.md` (sin
  trackear) — incluyen la documentación multi-shell PowerShell/Git Bash.
- `.env` modificado — verificar que no se commitea (está en `.gitignore`).

---

## P2 — Funcionalidad para "usable de verdad"

### BL-4 · Tool para crear vehículos
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

---

## Higiene documental

### BL-9 · Documentar spec-003 retroactivamente
M3 (Document Memory) está implementado y testeado pero no existe
`specs/003-document-memory/` — los specs saltan de 002 a 004. Recrear spec.md +
tasks.md a partir del código existente para completar el registro SDD.

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

---

## Fuera de alcance ("not yet" — no abrir sin decisión explícita)

GraphRAG, vector search, multi-agent, WhatsApp, web frontend, microservices,
event sourcing.
