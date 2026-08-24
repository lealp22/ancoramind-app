# Tasks: 005 — Calendar & Reminders

## Task Breakdown

### T1: Domain models
- [x] ReminderCreate, Reminder
- [x] CalendarEventCreate, CalendarEvent

### T2: Database
- [x] `ancora.reminders` table (trigger_at, status, provenance)
- [x] `ancora.calendar_events` table (start_at, end_at, provider_event_id)

### T3: CalendarProvider abstraction
- [x] CalendarProvider Protocol (create_event, list_events)
- [x] NoopCalendarProvider placeholder

### T4: Repositories
- [x] RemindersRepository — create, list_by_user (status filter)
- [x] CalendarRepository — create, list_range

### T5: Domain services
- [x] ReminderService — create_reminder, list_reminders
- [x] CalendarService — create_event (via provider), check_calendar

### T6: Tools (thin adapters, governance)
- [x] list_reminders (READ)
- [x] propose_reminder + execute_reminder (WRITE, confirmación)
- [x] check_calendar (READ)
- [x] propose_calendar_event + execute_calendar_event (EXTERNAL_ACTION, confirmación)

### T7: App wiring
- [x] 6 new tools registered in `_init_domain_tools()`
- [x] Total: 17 tools with ANCORA_DATABASE_URL

### T8: Tests
- [x] 68 unit tests (9 new)
- [x] ReminderService: create, list
- [x] CalendarService: create (provider call), check_calendar
- [x] Model validation (empty title fails)