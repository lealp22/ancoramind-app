# Verification: 011 — Todo Lists

> **Fecha:** 2026-09-10 · **Entorno:** Windows 11 (PowerShell) + venv Python 3.12
> **Estado:** ✅ verificado a nivel unitario (E2E Telegram pendiente — BL-18)

---

## Nota de proceso (SDD)

Esta spec se redactó **retroactivamente**: la implementación se construyó antes
de escribir `spec.md`/`tasks.md`, al interpretar "empieza a implementarlo" como
"empieza a codificar". El proceso correcto según BACKLOG.md ("cuando un item
pasa a en curso, se le asigna un número de spec y se trabaja con SDD:
spec.md → tasks.md → implementación") es **spec primero, código después**.
Para futuros items (p. ej. el nuevo BL-22 de FastAPI lifespan) se seguirá ese
orden. El contenido de la spec refleja fielmente lo construido, no al revés.

---

## Resultado

| Check | Resultado |
|---|---|
| `pytest tests/unit/` | ✅ **168 passed** (139 previos + 29 nuevos) |
| Tests nuevos unit | ✅ 12 models + 17 service/instructions |
| Integration (`test_todos_repo.py`, 7 tests) | ✅ colectan; SKIP sin Docker (patrón specs/009, igual que el resto de la suite) |
| `ruff check src/ tests/ scripts/` | ✅ limpio |
| `mypy` archivos nuevos | ✅ sin issues en los 5 ficheros nuevos (avisos en notes/reminders preexistentes, no tocados) |
| Registro de tools | ✅ log de arranque: `Todo tools registered… Total tools: 31` |
| Skill cargada | ✅ `assemble_instructions()` → 7 bloques, `test_todos_skill_loaded` verde |

## Qué se implementó

| Pieza | Fichero |
|---|---|
| `TodoList*` / `TodoItem*` (Pydantic v2) | `src/domain/todos/models.py` |
| `TodosService` (sin imports de Agno) | `src/domain/todos/service.py` |
| `TodosRepository` (`text()` + user-scoped) | `src/repositories/todos.py` |
| 12 tools (listas gobernadas + items directos) | `src/agent/tools/todos.py` |
| Registro (total 31 tools) | `src/main.py::_init_domain_tools()` |
| Skill + 7º bloque de instrucciones | `prompts/skills/todos.md`, `src/agent/instructions.py` |
| Tablas `todo_lists`/`todo_items` | `migrations/init.sql` |
| TRUNCATE de tablas nuevas | `tests/integration/conftest.py` |

## Decisiones tomadas durante la implementación

1. **Un solo `execute_todo_list`** para create/rename/delete (dispatch por
   `proposal.tool_name`) en vez de tres executors — menos superficie para el LLM.
2. **Items directos sin propose/execute**: reversibles como notes (memoria
   canónica sin efectos externos); solo las listas pasan por gobernanza.
3. **`position` por inserción** (`MAX+1`); `move_item` re-anexa al final.
   Reorden arbitrario queda como backlog futuro (la spec original mencionaba
   "reordenar (drag-and-drop lógica)" — alcance reducido conscientemente).
4. **`params: dict[str, Any]` + `getattr(result, "rowcount", 0)`** para pasar
   `mypy strict` donde SQLAlchemy devuelve `Any` (mismo patrón que el código
   existente, pero tipado explícito).

## E2E pendiente (bloqueado por BL-18)

1. Con la app corriendo y webhook/Telegram operativo: "Crea una lista Trabajo".
2. Confirmar con "Sí" → lista creada (`execute_todo_list`).
3. "Añade a Trabajo: preparar la presentación, prioridad alta".
4. "¿Qué tengo en Trabajo?" → items con estados/prioridades.
5. "Hecho lo de la presentación" → `done`; "Muéstrame mis listas" → conteos.
6. Verificar aislamiento: otro usuario no ve estas listas.
