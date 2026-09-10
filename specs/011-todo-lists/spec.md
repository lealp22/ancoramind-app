# Spec: 011 — Todo Lists

> **Backlog:** BL-21
> **Status:** implemented (2026-09-10)
> **Target:** múltiples listas TODO por usuario (`Trabajo`, `Personal`, ...) con
> items gestionables por el agente: `list/propose/execute_todo_list`
> (+rename/delete) y `list/add/update/complete/reopen/move/delete_todo_item`

---

## Requirement

El usuario necesita **listas de tareas persistentes** que pueda ir alimentando
por conversación ("Añade a Trabajo: preparar la presentación", "¿Qué tengo en
Personal?", "Hecho lo de comprar leche"). Los `reminders` (M5) no cubren este
caso: tienen trigger temporal + worker y son un disparo único, no gestión
activa de tareas. Las `notes` (M2) tampoco: son memoria sin estructura
(estado, prioridad, fecha límite, orden).

### Must Have

- Múltiples listas nombradas por usuario (crear / renombrar / eliminar).
- Items con: título, descripción opcional, estado (`pending`/`done`),
  prioridad opcional (`low`/`normal`/`high`), fecha límite opcional
  (`due_date`), orden manual (`position`).
- Operaciones de item: añadir, editar (parcial), completar, reabrir, mover
  a otra lista, eliminar; listar con filtros (`status`, `priority`).
- Gobernanza: crear/renombrar/eliminar **listas** → `propose_*`/`execute_*`
  con ActionProposal (WRITE, patrón §2.4). Operaciones de **item** → directas
  (mismo nivel de reversibilidad que notes: memoria canónica, sin efectos
  externos).
- Todo scoping por `user_id` resuelto de `RunContext` (nunca del LLM, §2.3).
- SQL solo `text()` parametrizado (§2.5); tablas nuevas en
  `migrations/init.sql` (idempotente).
- Skill `prompts/skills/todos.md` + registro en `assemble_instructions()`
  (cambio evaluable, §10.4).

### Should Have

- Persistencia canónica: tablas `ancora.todo_lists` + `ancora.todo_items`
  (borrado de lista en cascada a sus items).
- Conteo pendientes/totales en `list_todo_lists`.
- Tests unit (mocks) + integration (PostgreSQL real, patrón specs/009).

### Won't Have (esta spec)

- Reordenación drag-and-drop explícita (el orden es de inserción; mover entre
  listas re-anexa al final). Reordenar arbitrario = backlog futuro.
- Recordatorios automáticos sobre `due_date` (eso es `reminders`/BL-5).
- Listas compartidas entre usuarios (todo es user-scoped).
- Subtareas / items anidados.

---

## Design

```text
Telegram → Agno tool call → src/agent/tools/todos.py (thin adapters)
  ├── READ directo: list_todo_lists, list_todo_items
  ├── WRITE listas (gobernado): propose_todo_list[_rename|_delete]
  │     → action_proposals (pending_confirmation) → usuario "Sí"
  │     → execute_todo_list (confirm + dispatch por tool_name + mark_executed)
  └── Items directos: add/update/complete/reopen/move/delete_todo_item
        └── TodosService (src/domain/todos/, sin imports de Agno)
              └── TodosRepository (src/repositories/todos.py, text() + user_id)
                    └── ancora.todo_lists (1) ──< (N) ancora.todo_items
```

- **Un solo `execute_todo_list`** despacha por `proposal.tool_name`
  (`create/rename/delete_todo_list`) en vez de tres executors — menos
  superficie de tool para el LLM, misma auditoría.
- **`position`**: `COALESCE(MAX(position), -1) + 1` por lista al insertar;
  `move_item` re-anexa al final de la lista destino.
- **Propiedad de item** = propiedad de su lista: `create_item`/`list_items`
  verifican `get_list(user, list_id)`; `update/set_status/move/delete`
  filtran por `user_id` del item.
- **Prioridad como texto libre validado** (`low|normal|high`) en Pydantic +
  service (error claro al LLM en vez de 500).

## Success Criteria

1. "Crea una lista Trabajo" → `propose_todo_list` → "Sí" → `execute_todo_list` → lista creada.
2. "Añade a Trabajo: preparar la presentación, prioridad alta" → `add_todo_item` directo.
3. "¿Qué tengo en Trabajo?" → `list_todo_items` con estados y prioridades.
4. "Hecho lo de la presentación" → `complete_todo_item` → `done`.
5. "Mueve esa tarea a Personal" → `move_todo_item` entre listas propias.
6. Usuario B no ve ni toca listas/items del usuario A (aislamiento).
7. Suites unit + integration verdes; Ruff limpio; mypy limpio en archivos nuevos.
