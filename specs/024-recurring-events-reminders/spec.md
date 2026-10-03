# Spec: 024 — Eventos recurrentes, recordatorios recurrentes y snooze

> **Backlog:** BL-41
> **Status:** implemented locally (2026-10-03) — ver `verification.md`
> **Decisiones:** sin ADR nuevo — no cambia runtime/infraestructura, solo
> extiende los dominios `calendar`/`reminders` existentes (specs/005,
> specs/010/ADR-003).
> **Target:** permitir eventos de calendario y recordatorios con recurrencia
> simple (diaria/semanal/mensual/anual), vincular opcionalmente un recordatorio
> recurrente al crear un evento recurrente, posponer ("snooze") un recordatorio
> ya disparado, y evitar crecimiento indefinido de `reminders` purgando
> `fired` con más de 90 días.

---

## Requirement

Hoy `calendar_events` y `reminders` solo soportan ocurrencias únicas: no existe
"cada año", "cada semana" ni "cada mes". Un evento de calendario tampoco
dispara nunca un aviso de Telegram — solo lo hacen los recordatorios, y ambos
dominios están totalmente desacoplados (ningún tool ni servicio cruza entre
`CalendarService` y `ReminderService`). Esto no cubre casos de uso comunes:
cumpleaños que deberían avisar cada año, clases semanales, citas mensuales. La
recurrencia nunca fue discutida ni diferida explícitamente en specs/005 ni en
specs/010/ADR-003 — es un concepto nuevo.

### Must Have

- Módulo de dominio puro `src/domain/shared/recurrence.py`: `RecurrenceRule`
  (frecuencia `daily|weekly|monthly|yearly` + `interval` + `until` opcional),
  `next_occurrence(rule, after)`, `occurrences_in_range(rule, anchor, start, end)`,
  helpers de (de)serialización desde parámetros planos de tool.
- `CalendarEvent(Create)` y `Reminder(Create)` ganan `recurrence_rule`
  (columna JSONB nueva en ambas tablas).
- `check_calendar` expande recurrencia **virtualmente** en lectura (sin
  materializar filas futuras, sin worker/cron nuevo).
- Recordatorios recurrentes: al disparar con éxito, la fila `fired` queda como
  auditoría permanente (`fired_at` nuevo) y se inserta una fila `pending`
  nueva para la siguiente ocurrencia, enlazada por `recurrence_parent_id`
  (apunta siempre a la raíz de la cadena).
- Retención automática: el worker purga cada ciclo las filas `fired` con
  `fired_at` de más de 90 días — housekeeping de sistema, sin propuesta de
  usuario.
- Nuevo par gobernado `propose_reminder_snooze`/`execute_reminder_snooze`:
  crea una fila `pending` nueva con `trigger_at = ahora + N horas` (1–72h),
  sin recurrencia propia, enlazada por `recurrence_parent_id` a la raíz.
- `propose_calendar_event`/`execute_calendar_event` ganan parámetros
  opcionales de recurrencia + `with_reminder`/`reminder_lead_minutes` para
  crear, en la misma propuesta/confirmación, un recordatorio vinculado con la
  misma regla de recurrencia.
- Tests unitarios cubriendo recurrencia pura, repositorios, servicios, worker
  y tools (ver `tasks.md`).

### Should Have

- `prompts/skills/calendar.md` actualizado con ejemplos de recurrencia y
  vínculo con recordatorio.
- `prompts/skills/reminders.md` nuevo, documentando recurrencia y snooze.

### Won't Have (esta spec)

- RRULE/iCal (RFC 5545): se usa una regla simple (frecuencia + intervalo +
  fin). Sin proveedor de calendario real integrado hoy (`NoopCalendarProvider`),
  no se justifica esa complejidad ni la dependencia nueva.
- Materialización de ocurrencias futuras de eventos de calendario como filas
  reales, ni un worker/cron para calendario: expansión siempre virtual, en
  lectura.
- Edición/cancelación de una sola ocurrencia dentro de una serie recurrente
  (excepciones tipo "este martes no hay clase"): toda la serie se edita o
  ninguna.
- Migración a la Consent API nueva (specs/022/023) para calendar/reminders:
  se mantiene la API legacy de `ActionProposal` que ya usan hoy.
- Transacción atómica entre la creación del evento y la del recordatorio
  vinculado: son dos commits independientes (coherente con que ningún
  repositorio del proyecto cruza transacciones hoy); un fallo entre ambos deja
  el evento creado sin su recordatorio — limitación aceptada y documentada en
  el mensaje de respuesta del tool.
- Soporte multi-réplica del worker para la retención/avance de recurrencia
  (ya es una limitación aceptada preexistente de specs/010/ADR-003 para el
  disparo; se hereda sin cambios).
- Backfill de `fired_at` para filas `fired` previas a esta migración (nunca
  serán candidatas de retención).

---

## Design

```text
Lectura (check_calendar):
  CalendarRepository.list_range(uid, start, end)
    -> filas sin recurrencia: filtro por rango como hoy
    -> filas con recurrence_rule: occurrences_in_range(rule, anchor, start, end)
         genera copias virtuales (mismo id, start_at/end_at ajustados)
  CalendarService combina y ordena -> nunca se persiste una ocurrencia nueva

Escritura evento (propose/execute_calendar_event):
  payload += recurrence_frequency/interval/until, with_reminder, reminder_lead_minutes
  execute: CalendarService.create_event(..., recurrence_rule)
           si with_reminder: ReminderService.create_reminder(..., recurrence_rule)
           (dos commits independientes, orquestado en la capa de tool)

Disparo recordatorio recurrente (RemindersWorker.run_once):
  list_due -> notifier.send_reminder -> mark_fired(fired_at=now)
    si recurrence_rule: next_occurrence(rule, after=trigger_at)
      -> si no excede `until`: repo.create_next_occurrence (nueva fila pending,
         recurrence_parent_id = raíz)
  tras el ciclo: repo.delete_old_fired(before=now-90d)  [housekeeping, sin propuesta]

Snooze (propose/execute_reminder_snooze):
  propose: valida 1<=hours<=72, ActionProposal payload={reminder_id, hours}
  execute: ReminderService.snooze_reminder -> nueva fila pending,
           trigger_at=now+hours, recurrence_rule=None, recurrence_parent_id=raíz
```

- **Gobernanza:** avanzar a la siguiente ocurrencia y la purga por retención
  son transiciones internas de sistema (ejecución diferida de un consentimiento
  ya dado / housekeeping), igual que el disparo mismo en specs/010 — no crean
  una intención nueva del usuario, no requieren propuesta. Snoozear sí es una
  mutación nueva iniciada por el usuario → propose/execute obligatorio
  (AGENTS.md §7, sin excepciones por reversibilidad).
- **Dominio puro:** `src/domain/shared/recurrence.py` no importa Agno ni SQL;
  lo usan tanto `CalendarService`/`CalendarRepository` como
  `ReminderService`/`RemindersRepository`/`RemindersWorker`.
- **Independencia de dominios:** `CalendarService` y `ReminderService` no se
  referencian entre sí; la creación combinada vive en la capa de tool
  (`src/agent/tools/calendar.py`), que ya es el único lugar permitido para
  orquestar más de un servicio.

## Success Criteria

1. Un evento `yearly` creado con fecha pasada (ej. cumpleaños del año anterior)
   aparece en `check_calendar` al consultar el rango del año en curso, sin
   fila nueva en `calendar_events`.
2. `propose_calendar_event(..., recurrence_frequency="yearly", with_reminder=True)`
   confirmado crea un evento y un recordatorio vinculado con la misma regla.
3. Un recordatorio recurrente que se dispara con éxito queda `fired` con
   `fired_at` poblado, y aparece una fila `pending` nueva con el `trigger_at`
   correcto y `recurrence_parent_id` apuntando a la raíz; si la siguiente
   ocurrencia supera `until`, no se crea nada.
4. `propose_reminder_snooze`/`execute_reminder_snooze` confirmado crea una
   fila `pending` en `ahora + N horas`, sin recurrencia propia.
5. Tras 90 días desde `fired_at`, una fila `fired` deja de existir en el
   siguiente ciclo del worker; filas `fired` más recientes no se tocan.
6. Suite `pytest tests/unit/` verde, `ruff check` y `mypy src/` limpios
   (gates de CI, AGENTS.md §5).
7. `AGENTS.md` y `BACKLOG.md` referencian esta spec (BL-41/specs/024).
