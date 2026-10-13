# Skill — Todo Lists

## When to Use

- User mentions a task list ("mi lista Trabajo", "la lista de la compra")
- User wants a NEW list ("Crea una lista Personal", "Nueva lista Proyecto X")
- User wants to add something to a list ("Añade a Trabajo: ...")
- User asks what's in a list ("¿Qué tengo en Personal?")
- User finished something ("Hecho lo de ...", "Marca como completada ...")
- User wants to reorganize ("Mueve esa tarea a Personal", "Elimina esa tarea")

## Trivial Mutations (execute immediately, no confirmation)

Adding a title-only task to a list the user already has, and marking a task
done or reopened, run right away — call the tool and relay its result
directly. Never invent a "¿Confirmas?" question for these; the tool already
executed the action, so asking again would be lying about what happened:

- `propose_todo_item` with **only** `list_id` + `title` (no description, no
  priority, no due_date).
- `propose_todo_item_complete` / `propose_todo_item_reopen`.

Giving `propose_todo_item` a description, priority or due date switches it to
the reviewable path below instead — that extra data is worth checking before
it is saved.

## Reviewable Mutations (governed, require confirmation)

Creating, renaming and deleting LISTS; adding a task with description,
priority or due date; editing, moving or deleting ITEMS — all require
confirmation:

1. Call the matching `propose_*` tool — it creates the proposal and shows it.
   **You MUST call the propose_* tool.** NEVER write a proposal summary or
   confirmation request yourself — a proposal only exists if the tool created it.
2. Ask for "Sí" or the proposal's confirmation button.
3. The Core resolves consent and executes the proposal; no executor is available
   to the Agent. Multiple pending proposals require "Sí <ID>" or a specific button.
4. Only claim success after a verified Core result, never from the proposal alone.

Deleting a list also deletes its tasks — the proposal shows the count.
Mention it when relaying the proposal to the user.

## Disambiguation

- "mi lista" with several lists → show `list_todo_lists` and ask which one.
- "esa tarea" → use `list_todo_items` to resolve the exact item first.
- Priority vocabulary: alta → high, normal → normal, baja → low.
- Due dates: parse to ISO 8601 before calling the tool; if ambiguous, ask.
