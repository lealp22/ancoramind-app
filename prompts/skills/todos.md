# Skill — Todo Lists

## Available Tools

- `list_todo_lists` — show all TODO lists with pending/total counts
- `propose_todo_list` — propose a NEW list (requires confirmation)
- `execute_todo_list` — execute a confirmed list proposal
  (create, rename or delete depending on the proposal type)
- `propose_todo_list_rename` — propose renaming a list (requires confirmation)
- `propose_todo_list_delete` — propose deleting a list + its tasks
  (requires confirmation)
- `list_todo_items` — show tasks in a list (filters: status, priority)
- `add_todo_item` — add a task to a list
- `update_todo_item` — edit title, description, priority or due date
- `complete_todo_item` — mark a task as done
- `reopen_todo_item` — mark a task back as pending
- `move_todo_item` — move a task to another list
- `delete_todo_item` — delete a task

## When to Use

- User mentions a task list ("mi lista Trabajo", "la lista de la compra")
- User wants a NEW list ("Crea una lista Personal", "Nueva lista Proyecto X")
- User wants to add something to a list ("Añade a Trabajo: ...")
- User asks what's in a list ("¿Qué tengo en Personal?")
- User finished something ("Hecho lo de ...", "Marca como completada ...")
- User wants to reorganize ("Mueve esa tarea a Personal", "Elimina esa tarea")

## List Management (governed)

Creating, renaming and deleting LISTS requires confirmation:

1. Call `propose_todo_list` / `propose_todo_list_rename` /
   `propose_todo_list_delete` — it creates the proposal and shows it.
   **You MUST call the propose_* tool.** NEVER write a proposal summary or
   confirmation request yourself — a proposal only exists if the tool created it.
2. Wait for the user's confirmation ("Sí", "confirma", "vale").
3. Call `execute_todo_list` with the proposal ID from step 1 — the exact ID,
   never an invented one.
4. Only claim success after `execute_todo_list` returns it.

Deleting a list also deletes its tasks — the proposal shows the count.
Mention it when relaying the proposal to the user.

## Item Management (direct)

Adding, editing, completing, reopening, moving and deleting ITEMS executes
directly (same reversibility as notes — canonical memory, no external side
effects). Still resolve the list/item IDs from `list_todo_lists` /
`list_todo_items` — never invent UUIDs.

## Disambiguation

- "mi lista" with several lists → show `list_todo_lists` and ask which one.
- "esa tarea" → use `list_todo_items` to resolve the exact item first.
- Priority vocabulary: alta → high, normal → normal, baja → low.
- Due dates: parse to ISO 8601 before calling the tool; if ambiguous, ask.
