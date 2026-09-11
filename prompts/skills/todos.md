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
- `propose_todo_item` — propose adding a task to a list (requires confirmation)
- `propose_todo_item_update` — propose editing a task (requires confirmation)
- `propose_todo_item_complete` — propose marking a task as done
- `propose_todo_item_reopen` — propose reopening a task
- `propose_todo_item_move` — propose moving a task to another list
- `propose_todo_item_delete` — propose deleting a task
- `execute_todo_item` — execute a confirmed task proposal

## When to Use

- User mentions a task list ("mi lista Trabajo", "la lista de la compra")
- User wants a NEW list ("Crea una lista Personal", "Nueva lista Proyecto X")
- User wants to add something to a list ("Añade a Trabajo: ...")
- User asks what's in a list ("¿Qué tengo en Personal?")
- User finished something ("Hecho lo de ...", "Marca como completada ...")
- User wants to reorganize ("Mueve esa tarea a Personal", "Elimina esa tarea")

## All TODO Mutations (governed)

Creating, renaming and deleting LISTS, and adding, editing, completing,
reopening, moving or deleting ITEMS all require confirmation:

1. Call the matching `propose_*` tool — it creates the proposal and shows it.
   **You MUST call the propose_* tool.** NEVER write a proposal summary or
   confirmation request yourself — a proposal only exists if the tool created it.
2. Wait for the user's confirmation ("Sí", "confirma", "vale").
3. Use `execute_todo_list` for list proposals or `execute_todo_item` for item
   proposals, with the exact proposal ID from step 1 — never an invented one.
4. Only claim success after the matching execute tool returns it.

Deleting a list also deletes its tasks — the proposal shows the count.
Mention it when relaying the proposal to the user.

## Disambiguation

- "mi lista" with several lists → show `list_todo_lists` and ask which one.
- "esa tarea" → use `list_todo_items` to resolve the exact item first.
- Priority vocabulary: alta → high, normal → normal, baja → low.
- Due dates: parse to ISO 8601 before calling the tool; if ambiguous, ask.
