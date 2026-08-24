# Skill — Calendar

## Available Tools

- `check_calendar` — check calendar for a date or range
- `create_calendar_event` — create a new event (requires confirmation)

## When to Use

- User mentions an appointment, meeting, or event with a date/time
- User asks about their schedule
- User wants to add something to their calendar

## Event Creation

When creating an event:
1. Extract: title, date, time, duration (if mentioned)
2. Propose the event to the user with all details
3. Wait for explicit confirmation
4. Only claim success after the tool confirms creation

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