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
4. Call `execute_calendar_event` with the exact proposal ID
5. Only claim success after the execute tool confirms creation

Examples:
- "Tengo dentista el jueves a las 17:30"
- "Reunión con cliente el lunes a las 10"
- "¿Qué tengo esta semana?"

## Confirmation Required

Calendar events are EXTERNAL_ACTIONS. Always confirm before creating.

## Important

- Don't create events without a clear date/time
- If the date is ambiguous ("el jueves"), ask which Thursday
- Don't expose calendar provider details to the user