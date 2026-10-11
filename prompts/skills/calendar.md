# Skill — Calendar

## When to Use

- User mentions an appointment, meeting, or event with a date/time
- User asks about their schedule
- User wants to add something to their calendar

## Event Creation

When creating an event:
1. Extract: title, date, time, duration (if mentioned)
2. Call `propose_calendar_event` to persist the proposal and show its details
3. Wait for explicit confirmation
4. The Core validates consent and executes; do not call an executor
5. Only claim success after a verified Core result, never from the proposal alone

Examples:
- "Tengo dentista el jueves a las 17:30"
- "Reunión con cliente el lunes a las 10"
- "¿Qué tengo esta semana?"

## Recurring Events

Use `recurrence_frequency`/`recurrence_interval`/`recurrence_until` on
`propose_calendar_event` when the user implies repetition — recurring events
are never materialized as separate rows, they are expanded on the fly when
`check_calendar` is asked for a range, so a birthday created years ago still
shows up every year without any extra action.

Examples:
- "Cada año el 15 de marzo es mi cumpleaños" → `recurrence_frequency="yearly"`
- "Clase de yoga todos los lunes" → `recurrence_frequency="weekly"`
- "Revisión del coche cada 6 meses" → `recurrence_frequency="monthly"`, `recurrence_interval=6`
- "Hasta final de curso" → `recurrence_until` with that end date

## Linking a Reminder

If the user implies they also want to be *notified* (not just have it listed
in the calendar), pass `with_reminder=True` on the same `propose_calendar_event`
call — one proposal/confirmation creates both the event and a linked
reminder with the same recurrence. Use `reminder_lead_minutes` if they want
the notice before the event instead of exactly at its start.

Examples:
- "Recuérdame cada año el cumpleaños de mi madre el 10 de mayo" →
  `recurrence_frequency="yearly"`, `with_reminder=True`
- "Avísame 30 minutos antes de la reunión" → `with_reminder=True`,
  `reminder_lead_minutes=30`

Don't infer `with_reminder=True` just because the event has a date — only
when the user's wording implies they want to be actively notified, not just
have it on the calendar.

## Confirmation Required

Calendar events are EXTERNAL_ACTIONS. Always confirm before creating.

## Important

- Don't create events without a clear date/time
- If the date is ambiguous ("el jueves"), ask which Thursday
- Don't expose calendar provider details to the user
- The Core creates a calendar event and its linked reminder in one transaction.
  A failed linked reminder rolls back the event too; never claim success on failure.
