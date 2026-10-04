# Skill — Reminders

## When to Use

- User wants to be reminded of something at a specific time
- User asks what reminders they have
- A reminder just fired and the user wants it to come back later ("snooze")

## Reminder Creation

When creating a reminder:
1. Extract: title, date/time, optional recurrence
2. Call `propose_reminder` to persist the proposal and show its details
3. Wait for explicit confirmation
4. Call `execute_reminder` with the exact proposal ID
5. Only claim success after the execute tool confirms creation

Examples:
- "Recuérdame llamar al dentista el jueves a las 17:00"
- "Avísame de la revisión del coche en 2 semanas"
- "¿Qué recordatorios tengo?"

## Recurrence

Use `recurrence_frequency`/`recurrence_interval`/`recurrence_until` on
`propose_reminder` when the user implies repetition. A recurring reminder
keeps its fired occurrences as a permanent record and automatically creates
the next pending one once it fires — no action needed from you after
creation.

Examples:
- "Recuérdame cada año el cumpleaños de mi madre el 10 de mayo" →
  `recurrence_frequency="yearly"`
- "Avísame cada semana para regar las plantas" → `recurrence_frequency="weekly"`

If the user actually wants the reminder tied to something visible on their
calendar too (not just a notification), consider `propose_calendar_event`
with `with_reminder=True` instead — see the calendar skill.

## Snoozing

When a reminder has already fired and the user wants to be reminded again
later (e.g. "recuérdamelo en 20 minutos", "avísame otra vez en 2 horas"),
this is a **different** operation from recurrence — it never
changes when the reminder's own cadence fires next (snoozing a yearly
birthday reminder a few hours does not move next year's occurrence).

1. If you don't already know the reminder's ID from context, call
   `list_reminders` (optionally `status="fired"`) to find it
2. Call `propose_reminder_snooze` with that `reminder_id` and the number of
   minutes (5-10,080; up to 7 days)
3. Wait for explicit confirmation
4. Call `execute_reminder_snooze` with the exact proposal ID

Examples:
- "Recuérdamelo dentro de 20 minutos"
- "Posponlo 1 hora"

## Confirmation Required

Creating a reminder (WRITE) and snoozing one are both governed mutations —
always confirm before calling the corresponding `execute_*` tool.

## Important

- Don't create a reminder without a clear date/time
- Snoozing is independent of recurrence — never use it as a substitute for
  setting `recurrence_frequency` on a repeating reminder
- Advancing a recurring reminder to its next occurrence and purging old
  fired reminders (after 90 days) both happen automatically in the
  background worker — never something you need to call a tool for
