# Verification: 035 — Subclasificación WRITE_TRIVIAL / WRITE_REVIEWABLE

> Fecha: 2026-10-13

## Automatizada

- `pytest tests/unit/` → **1329 passed** (0 fallos, 0 omitidos). Archivos
  nuevos/ampliados por esta spec:
  - `tests/unit/test_proposal_consent_model.py` (+2: round-trip de
    `ConsentMode` y sincronía con el `CHECK` de la migración 0014).
  - `tests/unit/test_trivial_executor.py` (nuevo, 6 tests: alcance exacto de
    `TRIVIAL_MUTATIONS`, rechazo fuera de alcance, éxito con 1 solo commit,
    fallo "no encontrado" sin auditoría, fallo inesperado sin reintento, y
    fallo de la auditoría revirtiendo también la mutación).
  - `tests/unit/test_todos_tools.py` (+2, -1: nuevo test de la rama trivial
    de `propose_todo_item`, nuevo test de `complete`/`reopen` vía
    `TrivialExecutor`, y el test de regresión de `move`/`delete` que
    confirma que siguen siendo `WRITE_REVIEWABLE`; se retiró el test que
    verificaba que `complete`/`reopen` creaban `ActionProposal`, porque ya
    no es el comportamiento real).
  - `tests/unit/test_note_tools.py` (reescrito el test de `propose_note`
    para la rama trivial; el resto de tests de `search_notes`/`execute_note`
    sin cambios).
  - `tests/unit/test_tool_sessions_and_errors.py` (1 aserción corregida:
    comprobaba texto literal del docstring anterior de `propose_note`).
- `ruff check src/ tests/ scripts/ migrations/` → limpio.
- `mypy src/` → limpio (167 archivos).
- `python -c "from src.main import app"` → import limpio (confirma que el
  wiring nuevo de `TrivialExecutor` dentro de `todos.py`/`notes.py` no rompe
  el arranque de la app).
### Evidencia original — 2026-10-13

- `pytest tests/integration/ --collect-only` → **158 tests** recolectados
  sin error (incluye los 2 nuevos de
  `test_actions_repo.py::test_create_self_authorized_*`). **No se ejecutaron**
  contra PostgreSQL real: esta sesión no tiene Docker disponible
  (`docker info` falla). Quedan preparados con las aserciones completas
  (no comitea por su cuenta, dos filas `self_authorized` con
  `confirming_interaction_id=NULL` no colisionan con el índice único) para
  cuando haya infraestructura.
- Migración `0014_write_trivial_consent_mode`: verificada con
  `alembic.script.ScriptDirectory` que es el head único, encadenada a
  `0013_session_token_index`, sin fork. **No se aplicó** contra PostgreSQL
  real (mismo motivo: sin Docker en esta sesión) — `migrations/init.sql` se
  actualizó en paralelo con el mismo bloque DDL, pero su equivalencia con
  `alembic upgrade head` tampoco se verificó end-to-end
  (`test_init_sql_is_compatible_with_alembic_head` requiere Postgres).

### Revalidación PostgreSQL — 2026-10-15

- `pytest tests/integration/` → **159 passed, 1 skipped**; la omisión es STT
  live opt-in, no falta de PostgreSQL.
- `pytest tests/integration/test_actions_repo.py` → **9 passed**, incluidos los
  dos casos `create_self_authorized` y los dos de `list_pending`.
- `pytest tests/integration/test_migrations.py` → **4 passed**: fresh install,
  upgrade con datos, downgrade de la última revisión e equivalencia de init SQL.
- Supabase productivo está en head `0015_ancora_rls_hardening`, por lo que
  `0014_write_trivial_consent_mode` también está aplicado.

## Estado de gates

- [x] `alembic upgrade head` / `downgrade -1` contra PostgreSQL real,
  confirmando que
  `test_alembic_fresh_install_and_latest_downgrade` y
  `test_init_sql_is_compatible_with_alembic_head` pasan con la nueva
  revisión.
- [x] `pytest tests/integration/test_actions_repo.py` contra Postgres real,
  en particular los 2 tests nuevos de `create_self_authorized`.
- [x] Validación E2E Telegram del camino trivial: alta título-solo en lista
  existente, completar/reabrir y guardar/buscar nota sin confirmación ni botones.
  Campaña asistida autorizada 2026-10-16, runtime 8/r4; evidencia debajo.
- [x] Regresión E2E reviewable con prioridad y prioridad+fecha: propuestas
  pendientes sin escritura previa y consentimiento Core, specs/036 pasos 2/8/9.
- [ ] Variantes E2E restantes del gate original: `description` y fecha-sola
  informadas; cubiertas por tests locales, no ejecutadas en esta campaña.

## Success Criteria (spec.md) — estado

1. ✅ `WRITE_TRIVIAL` documentado en `AGENTS.md` §2.4 y
   `docs/governance.md`, con el criterio y los 3 ejemplos de esta
   iteración.
2. ✅ Vía de ejecución nueva (tool → `TrivialExecutor` → `apply_mutation` +
   `create_self_authorized`, 1 transacción) sin tocar
   `claim_confirmation`/`ProposalExecutor` — cubierto por
   `test_trivial_executor.py` y, para la auditoría, por
    `test_actions_repo.py` (verificado contra Postgres real).
3. ✅ Alcance exacto implementado: `propose_todo_item` (solo título, lista
   existente), `propose_todo_item_complete`/`reopen`, `propose_note` —
   siempre triviales; `propose_todo_item` con algún campo opcional,
   `propose_todo_item_move`/`delete`, `propose_todo_list*` — sin cambios
   (`WRITE_REVIEWABLE`). Cubierto por `test_todos_tools.py`/
   `test_note_tools.py`.
4. ✅ Ninguna mutación trivial puede quedar sin su fila de auditoría ni
   viceversa — cubierto por
   `test_audit_row_failure_also_rolls_back_the_mutation` y
   `test_target_not_owned_rolls_back_and_audits_nothing`.
5. ✅ Nombres de tool sin cambios (decisión del propietario, 2026-10-13) —
   solo cambiaron docstrings y `prompts/skills/todos.md`.
6. ✅ `pytest`/`ruff`/`mypy` verdes; integración y migraciones verificadas
   contra PostgreSQL real.
7. ✅ `AGENTS.md`/`BACKLOG.md` referencian BL-46/specs/035 con el alcance
    real entregado.

## Refuerzo transaccional PostgreSQL — 2026-10-16

Cuatro pruebas nuevas en `tests/integration/test_trivial_executor.py` ejecutan
`TrivialExecutor` con servicios y repositorios reales, sin simular `apply_mutation`:

- Alta título-solo en lista existente, completar y reabrir, más nota: los cuatro
  efectos se persisten con su auditoría `self_authorized`/`executed`, hash válido,
  sin presentación ni interacción de confirmación.
- Lista de otro usuario: no aparece tarea ni auditoría del solicitante.
- Fallo inyectado después del INSERT real de auditoría: rollback de nota y fila
  de auditoría, sin retry. Cubre atomicidad real, no solo `rollback.assert_awaited`.
- Fallo inyectado antes de commit: ni la mutación ni su auditoría sobreviven.
  No simula pérdida de conexión después de commit ni afirma resolver ambigüedad
  de una confirmación de commit perdida.

El procesador también conserva una escritura trivial ya confirmada en DB si
posteriormente falla `present_reply`: aviso fijo sin afirmar el efecto ni
reintentar, una sola nota y una sola auditoría tras recuperación. Cubierto en
`tests/integration/test_proposal_presentation.py`.

Validación global: **1428 unitarias; 173 integraciones PostgreSQL superadas,
1 STT live omitida por diseño**; Ruff/mypy limpios. Sin cambios de ejecución,
prompts ni esquema. **BL-46 sigue pendiente de matriz E2E Telegram**: estos tests
no acreditan clasificación de riesgo ni respuesta semántica del modelo real.

## E2E Telegram asistido autorizado — 2026-10-16

AC7 de specs/036, paso 10, ejecutado mediante UI Telegram Web/Playwright con
autorización exclusiva del propietario. Runtime revisión 8,
`ancoramind-default-r4`; sin cambios de código/configuración ni fixtures SQL.

- Alta título-solo: interacción `59c7c657-cf00-4e50-b22d-eea51b1ebbf1`,
  auditoría `940bf75a-0764-430e-a5c3-2ef58868b196`, crea exactamente una tarea
  `db15bec2-e8c4-4928-a9fe-afee85260a89` («Validar reapertura AC7»), sin
  prioridad, descripción ni fecha en la lista de campaña existente.
- Completar: `18ef6ff6-8758-4504-967e-305266341ce8`, auditoría
  `cf6dd134-547f-4e5b-a1ff-d8e3fb770a76`, estado `done` verificado.
- Reabrir: `751395e6-6c46-4930-996d-47c41dc07128`, auditoría
  `bf571553-b8ba-4dd2-bfeb-9681a518f794`, mismo ID vuelve a `pending`.
- Guardar nota: `3c95c1ae-7508-4fe0-b407-4ccc0d5a395b`, auditoría
  `b5426857-22c3-41f9-80bf-2ae68b903b4b`. Una sola nota canónica
  `0f4bf955-0fb1-4ea7-b761-6cdb8ed494b3` con contenido exacto «Prueba
  sintética AC7 del 16 de octubre de 2026: comprobar memoria de notas».
- Consulta lista `0920cd15-d798-42f9-bbf5-f6e4737b60b4` muestra las dos tareas
  pendientes (póliza AC3 intacta y reapertura). Búsqueda
  `94d41296-25f2-4a43-99ea-b7d3694cb63d` devuelve el contenido exacto de nota;
  ninguna consulta crea auditoría. No se infieren tools concretas del contador.
- Cuatro mutaciones, cuatro auditorías `self_authorized`/`executed`, origen
  en su interacción y bot/chat correctos, timestamps terminales y hashes
  recalculados con `payload_hash` **4/4 válidos**; sin presentación ni
  confirmación. Respuestas DOM sin petición de consentimiento ni botones.
- Las seis interacciones `completed`, ruta r4/revisión 8, cero retries;
  `agent_final` y un chunk completados con message ID, sin aviso de fallo.
  Foto final 15:37:23 UTC: una tarea AC7 y una nota, sin duplicación, cero
  propuestas confirmables y ninguna auditoría reviewable nueva.

**Camino trivial E2E superado en esta ejecución asistida**. Los datos quedan
guardados por decisión del propietario. No se prueba rollback/concurrencia
en producción ni se cierra BL-46: las variantes reviewable restantes y la
revisión final de gates siguen explícitas arriba; BL-48 conserva su matriz propia.
