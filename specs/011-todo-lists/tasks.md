# Tasks: 011 — Todo Lists

## T1: Domain models

- [x] `src/domain/todos/__init__.py`
- [x] `TodoListCreate`, `TodoListRename`, `TodoList` (`models.py`)
- [x] `TodoItemCreate`, `TodoItemUpdate`, `TodoItem` (`models.py`)
- [x] Prioridad validada `low|normal|high`; opcionales con `X | None = None`

## T2: Database

- [x] `ancora.todo_lists` (user_id, name, timestamps) + índice por user_id
- [x] `ancora.todo_items` (list_id FK CASCADE, user_id, title, description,
      status, priority, due_date, position, timestamps) + índices
- [x] Todo en `migrations/init.sql` (idempotente, `IF NOT EXISTS`)

## T3: Repository

- [x] `src/repositories/todos.py`: `TodosRepository`
- [x] Listas: create/list/get/rename/delete (user-scoped)
- [x] Items: create (append `MAX(position)+1`, verifica propiedad de lista),
      list (filtros status/priority, `None` si lista ajena),
      get/update (parcial)/set_status/move (re-anexa al final)/delete
- [x] Solo `text()` con bind params; ownership vía `get_list` + `user_id`

## T4: Domain service

- [x] `src/domain/todos/service.py`: `TodosService` (repo por constructor)
- [x] `create_list`/`list_lists`/`rename_list`/`delete_list` (strip de nombres)
- [x] `add_item`/`list_items`/`update_item`/`set_item_status`/`move_item`/
      `delete_item` (validación `status`/`priority`, `None` si lista ajena)

## T5: Tools (thin adapters, gobernanza)

- [x] `src/agent/tools/todos.py` (12 tools, docstrings ES con ejemplos)
- [x] READ: `list_todo_lists` (conteo pendientes/totales), `list_todo_items`
- [x] WRITE listas (propose/execute): `propose_todo_list`,
      `propose_todo_list_rename`, `propose_todo_list_delete`,
      `execute_todo_list` (dispatch por `tool_name` + `mark_executed`)
- [x] Items directos: `add/update/complete/reopen/move/delete_todo_item`
      (parseo UUID + fechas ISO con mensajes de error en ES)

## T6: App wiring + prompts

- [x] 12 tools registradas en `_init_domain_tools()` (total: 31)
- [x] `prompts/skills/todos.md` (listas gobernadas vs items directos,
      desambiguación, vocabulario es→enum) + `assemble_instructions()` (7 bloques)

## T7: Tests

- [x] `tests/unit/test_todos_models.py` (12): validación create/rename/item,
      rechazo de prioridad/título vacío, `from_attributes`
- [x] `tests/unit/test_todos_service.py` (15+2): CRUD listas + items con mocks
      (`AsyncMock(spec=TodosRepository)`), filtros, rechazos `ValueError`,
      enforcement de `UserContext` (trusted-user-from-channel)
- [x] `tests/unit/test_instructions.py`: conteo 7 bloques + `todos_skill_loaded`
- [x] `tests/integration/test_todos_repo.py` (7): create/list/rename/delete,
      item lifecycle (positions, filtros, done, update, delete), user-scoping,
      move entre listas, cascade delete
- [x] `tests/integration/conftest.py`: TRUNCATE incluye `todo_items/todo_lists`
- [x] Resultado: **168 unit passed**, Ruff limpio, mypy limpio en archivos
      nuevos (avisos en notes/reminders preexistentes, no tocados)

## T8: Docs + verificación

- [x] BACKLOG.md: BL-21 marcado implementado (2026-09-10)
- [x] `specs/011-todo-lists/spec.md` (esta spec, creada retroactivamente tras
      la implementación — ver nota en `verification.md`)
- [ ] Validación E2E en Telegram (propose→"Sí"→execute + CRUD items):
      **pendiente — bloqueado por BL-18** (igual que M3–M5)
- [x] `verification.md` con checklist SDD
