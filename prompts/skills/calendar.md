# Skill — Calendar

## When to Use

- User mentions an appointment, meeting, or event with a date/time
- User asks about their schedule
- User wants to add something to their calendar

## Event Creation

When creating an event:
1. Extract: title, date, time, duration (if mentioned)
2. Call `propose_calendar_event` to persist the proposal and show its details
3. The Core shows the stored proposal and confirmation controls; do not
   duplicate its fields or confirmation question in your answer
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

`recurrence_interval` is an integer from 1 to 365 (default 1).
`recurrence_until`, if supplied, is an **inclusive** upper bound: a
timezone-aware ISO 8601 datetime with an explicit offset or Z, for example
`2026-11-15T10:00:00+01:00`. Preserve the user's explicit time and offset;
an equivalent UTC instant is valid too. Do not reduce it to a date or remove
its timezone. Date-only and naive datetime values are rejected by the Core.
For an end date whose time or timezone is unclear, ask for clarification in natural language.
Do not invent midnight or UTC, silently drop the limit, or require the user
to supply tool parameter names. Omit the bound only for genuinely open-ended recurrence.

Examples:
- "Cada año el 15 de marzo es mi cumpleaños" → `recurrence_frequency="yearly"`
- "Clase de yoga todos los lunes" → `recurrence_frequency="weekly"`
- "Revisión del coche cada 6 meses" → `recurrence_frequency="monthly"`, `recurrence_interval=6`
- "Hasta final de curso" → clarify the last date, time and timezone if unclear
  before setting `recurrence_until`

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

Calendar events are EXTERNAL_ACTIONS. The Core requires consent before creating;
the Agent does not ask a second confirmation question.

## Important

- Don't create events without a clear date/time
- If the date is ambiguous ("el jueves"), ask which Thursday
- Don't expose calendar provider details to the user
- The Core creates a calendar event and its linked reminder in one transaction.
  A failed linked reminder rolls back the event too; never claim success on failure.
