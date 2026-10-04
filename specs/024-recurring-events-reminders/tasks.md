# Tasks: 024 — Eventos recurrentes, recordatorios recurrentes y snooze

## T1: Módulo de recurrencia (dominio puro)

- [x] `src/domain/shared/__init__.py` (paquete nuevo).
- [x] `src/domain/shared/recurrence.py`: `RecurrenceFrequency(StrEnum)`,
      `RecurrenceRule(BaseModel)` (`frequency`, `interval: int` 1–365,
      `until: datetime | None` tz-aware validado).
- [x] `next_occurrence(rule, anchor, after) -> datetime | None` — clamp
      siempre desde el día del **ancla** explícito (no desde `after`); `None`
      si supera `until`. (Firma final añade `anchor` explícito frente al
      `after`-only del plan original, necesario para evitar deriva real en
      cadenas de varias ocurrencias — ver `_step_monthly`.)
- [x] `occurrences_in_range(rule, anchor_start, range_start, range_end, max_iterations=10_000) -> list[datetime]`
      — soporta ancla en el pasado; acotado por `max_iterations`.
- [x] `recurrence_rule_from_flat(frequency, interval, until)` /
      `recurrence_rule_to_flat(rule)` + `rule_to_jsonb_param(rule)` (helper
      añadido para serializar a `CAST(:param AS jsonb)` sin duplicar
      `json.dumps` en los dos repositorios).
- [x] Tests `tests/unit/test_recurrence.py` (16 tests): clamp día-31
      mensual, 29-feb anual en año no bisiesto, límite inclusive de `until`,
      intervalo > 1, ancla pasada generando ocurrencias en rango actual,
      round-trip flat↔RecurrenceRule, frecuencia inválida.

## T2: Modelos Pydantic

- [x] `src/domain/calendar/models.py`: `recurrence_rule: RecurrenceRule | None`
      en `CalendarEventCreate`/`CalendarEvent`. Sin validador `mode="before"`:
      Pydantic v2 parsea un dict JSONB directamente en un `BaseModel` anidado,
      confirmado con test — el validador explícito del plan no era necesario.
- [x] `src/domain/reminders/models.py`: `recurrence_rule`,
      `recurrence_parent_id` en `ReminderCreate`; los mismos + `fired_at` en
      `Reminder`.
- [x] Tests: extendido `test_reminder_calendar_models.py` (+4 tests).

## T3: Migración

- [x] `migrations/versions/0007_recurrence_snooze.py`
      (`down_revision="0006_proposal_consent"`): columnas
      `calendar_events.recurrence_rule`, `reminders.recurrence_rule`,
      `reminders.recurrence_parent_id` (FK autoreferenciada,
      `ON DELETE SET NULL`), `reminders.fired_at`; índices
      `idx_calendar_recurrence`, `idx_reminders_fired_at` (parciales).
      `downgrade()` simétrico. Aplicada y verificada contra Postgres real
      (ver `verification.md`).
- [x] `migrations/init.sql` actualizado para quedar equivalente a `head`.

## T4: Repositorios

- [x] `src/repositories/calendar.py`: `list_range` con
      `OR recurrence_rule IS NOT NULL`; `create()` persiste
      `recurrence_rule`; `_row_to_event` lo mapea.
- [x] `src/repositories/reminders.py`: `create()` persiste `recurrence_rule`/
      `recurrence_parent_id`; `_row_to_reminder` mapea los 3 campos nuevos;
      `mark_fired()` setea `fired_at=:now`; nuevo `get_by_id(user_id, id)`;
      nuevo `create_next_occurrence(fired, next_trigger_at)` y
      `create_snoozed(original, trigger_at, source_action_id)` (comparten
      `_insert_followup` privado); nuevo `delete_old_fired(before) -> int`
      (sin scope por `user_id`, comentado explícitamente el motivo).
- [x] Tests de repositorio: la guarda `RETURNING` ya cubierta por
      `test_repository_returning_guards.py` (sin cambios necesarios); el resto
      de métodos nuevos se ejercitan indirectamente vía los tests de servicio/
      worker (mocks) y, de extremo a extremo, vía la suite de integración
      (94 tests, incluye `test_calendar_repo.py`/`test_reminders_repo.py`
      contra Postgres real con el esquema de `init.sql` ya actualizado) +
      verificación manual (`verification.md`).

## T5: Servicios

- [x] `CalendarService.check_calendar`: expande recurrencia virtualmente
      (`occurrences_in_range` + `model_copy`), combina y ordena con las no
      recurrentes.
- [x] `ReminderService.create_reminder`: parámetro `recurrence_rule` opcional.
- [x] `ReminderService.snooze_reminder(user_context, original_id, minutes, proposal_id) -> Reminder | None`
      — valida propiedad vía `get_by_id` + `UserContext`, valida `5<=minutes<=10080`
      vía `SnoozeRequest(BaseModel)`, sin restricción por `status`. Devuelve
      `None` si no existe/no es del usuario (convención ya usada en
      `domain/vehicles` — se descarta una excepción `NotFound` nueva).
- [x] **Desviación respecto al plan**: `ReminderService.create_next_occurrence`
      no se implementó como método de servicio — la lógica de avance de
      recurrencia vive directamente en `RemindersWorker._advance_recurrence`
      hablando con `RemindersRepository`, para no introducir `ReminderService`
      como dependencia nueva del worker (preserva el aislamiento
      ADR-001/ADR-003 explícitamente exigido en T6). Mantenerla en el
      servicio además habría sido código muerto sin otro consumidor.
- [x] Tests: extendido `test_reminder_calendar_service.py` (+6 tests:
      expansión con ancla pasada, exclusión no-recurrente, corte por `until`,
      snooze feliz/no-encontrado/fuera-de-rango).

## T6: Worker

- [x] `src/domain/reminders/worker.py`: constante `RETENTION_DAYS = 90`;
      tras `mark_fired` exitoso, si `recurrence_rule`, calcula la siguiente
      ocurrencia (ancla = raíz de la cadena vía `get_by_id` si tiene
      `recurrence_parent_id`) y crea la fila siguiente si no excede `until`;
      tras el ciclo, `repo.delete_old_fired(before=now-90d)` (log solo si
      `deleted > 0`). Sin `ReminderService` como dependencia del worker.
- [x] Tests: extendido `test_reminder_worker.py` (+5 tests: no-recurrente sin
      cambios, recurrente avanza, respeta `until`, ancla de hijo usa la raíz
      — caso explícito de no-deriva día-31→28→31 —, retención se invoca cada
      ciclo).

## T7: Tools

- [x] `src/agent/tools/calendar.py`: `propose_calendar_event` gana
      `recurrence_frequency`/`recurrence_interval`/`recurrence_until`,
      `with_reminder`, `reminder_lead_minutes`; docstring en español con
      ejemplos. `execute_calendar_event` reparsea y, si `with_reminder`, crea
      el recordatorio vinculado vía nuevo `_get_reminder_service()` y
      `_create_linked_reminder()`; captura y reporta explícitamente el caso
      de fallo parcial (evento creado, recordatorio no) sin ocultarlo.
- [x] `src/agent/tools/reminders.py`: `propose_reminder`/`execute_reminder`
      ganan los mismos 3 parámetros de recurrencia. Nuevo par
      `propose_reminder_snooze`/`execute_reminder_snooze` (valida 5 min–7 días,
      payload `{reminder_id, minutes}`, gobernado vía `ActionProposal` legacy).
      `list_reminders` ahora muestra el ID de cada recordatorio (necesario
      para que el flujo de snooze sea usable) y un marcador 🔁 si recurre.
- [x] Tests de tools: nuevo `test_calendar_reminder_recurrence_tools.py`
      (9 tests) — round-trip de payload para los 3 pares, creación combinada
      evento+recordatorio (éxito y fallo parcial no oculto), snooze fuera de
      rango, snooze execute no-encontrado, y el **test de seguridad
      obligatorio**: `execute_reminder_snooze` usa `UserContext` del
      `run_context` para la propiedad, nunca el `reminder_id` del payload
      almacenado.

## T8: Registro en `main.py`

- [x] `_init_domain_tools()`: importados y registrados
      `propose_reminder_snooze`/`execute_reminder_snooze`; log de registro
      actualizado.

## T9: Prompts

- [x] `prompts/skills/calendar.md`: secciones "Recurring Events" y "Linking
      a Reminder" + ejemplos; nota sobre el fallo parcial no atómico en
      "Important".
- [x] `prompts/skills/reminders.md` (nuevo): misma estructura que
      `calendar.md` — When to Use / Reminder Creation / Recurrence / Snoozing
      / Confirmation Required / Important.

## T10: Verificación y documentación

- [x] `pytest tests/unit/` (684 tests), `ruff check src/ tests/unit/ migrations/`,
      `mypy src/` (114 archivos) — todo verde.
- [x] Verificación manual contra PostgreSQL real (Docker local, suite de
      integración completa: 94 tests) tras aplicar la migración — ver
      `verification.md` para el detalle y una nota sobre dónde se aplicó.
- [x] `AGENTS.md` §3 (añadido `024-recurring-events-reminders`) + contador
      de tests actualizado (684); `BACKLOG.md` (nueva entrada BL-41 +
      contador de tests) actualizados.
- [x] `verification.md` escrito.
