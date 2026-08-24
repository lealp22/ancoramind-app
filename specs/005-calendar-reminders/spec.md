# Spec: 005 — Calendar & Reminders

> **Milestone:** M5 — Calendar & Reminder capabilities
> **Status:** implemented
> **Target:** `create_calendar_event` (EXTERNAL_ACTION) + `create_reminder` (WRITE) + `check_calendar` / `list_reminders`

---

## Requirement

Añadir capacidades de calendario y recordatorios con gobernanza.

### Must Have

- Calendar: `check_calendar` (READ), `create_calendar_event` (EXTERNAL_ACTION, confirmación)
- Reminders: `list_reminders` (READ), `create_reminder` (WRITE, confirmación)
- `CalendarProvider` Protocol (desacopla del SDK externo)
- `NoopCalendarProvider` placeholder para POC
- Action proposal pattern: propose → confirm → execute
- Source provenance (document_id)

### Should Have

- Canonical persistence: `reminders` + `calendar_events` tables
- Date range queries for calendar

### Won't Have

- Real external calendar provider (Google/Outlook)
- Background scheduler for reminders (futuro: AgentOS Scheduler, cron, queue)

---

## Success Criteria

1. "Recuérdame llamar al dentista" → `propose_reminder` → confirmación → `execute_reminder`
2. "Tengo dentista el jueves 17:30" → `propose_calendar_event` → confirmación → `execute_calendar_event`
3. "¿Qué recordatorios tengo?" → `list_reminders` desde PostgreSQL
4. "¿Qué tengo el jueves?" → `check_calendar` desde PostgreSQL
5. Provider abstraction permite futuro swap a Google/Outlook sin reescribir el dominio