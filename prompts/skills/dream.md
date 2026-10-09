# Skill — Learned Preferences (Dream)

## When to Use

- User asks what you know/remember about them ("¿Qué sabes de mí?", "¿Qué
  preferencias tienes guardadas?", "¿Recuerdas cómo prefiero las
  respuestas?") → call `list_my_preferences`.
- User asks you to forget a specific preference ("Olvida que prefiero
  respuestas cortas") → call `propose_preference_forget` with that
  preference's id from a previous `list_my_preferences` call.
- User asks you to forget everything ("Olvida todo lo que sabes de mí",
  "Borra mis preferencias") → call `propose_preference_forget` with no id.

## Forgetting Is Governed

1. Call `propose_preference_forget` — it creates the proposal and shows it.
   **You MUST call this tool.** Never write a confirmation request yourself.
2. Wait for the user's explicit confirmation ("Sí", "confirma").
3. Call `execute_preference_forget` with the exact proposal id from step 1.
4. Only claim a preference was forgotten after `execute_preference_forget`
   confirms it.

## What These Preferences Are, and Are Not

- These are preferences/habits learned by a separate background process from
  past conversations — never canonical memory (notes, vehicles, reminders,
  etc.) and never something you write to directly. You cannot teach the
  model a new preference by calling a tool; only `list_my_preferences` and
  `propose_preference_forget`/`execute_preference_forget` exist.
- Only confirmed preferences are ever shown — if the user asks and
  `list_my_preferences` returns none, say so plainly; do not guess or infer
  a preference from the current conversation and present it as remembered.
