# Verification: 024 — Eventos recurrentes, recordatorios recurrentes y snooze

> Fecha: 2026-10-03

## Automatizada

- `pytest tests/unit/` → **684 passed** (643 preexistentes + 41 nuevos:
  16 en `test_recurrence.py`, 4 en `test_reminder_calendar_models.py`, 6 en
  `test_reminder_calendar_service.py`, 5 en `test_reminder_worker.py`, 9 en
  `test_calendar_reminder_recurrence_tools.py`, 1 ajuste indirecto).
- `ruff check src/ tests/unit/ migrations/` → limpio.
- `mypy src/` → limpio (114 archivos).
- `pytest tests/integration/` (Docker Postgres local, DB dedicada
  `ancoramind_test` vía `migrations/init.sql` ya actualizado) → **94 passed**,
  sin regresiones.

## Manual contra PostgreSQL real

Se aplicó `alembic upgrade head` (revisión `0007_recurrence_snooze`) contra
la base configurada en `ANCORA_DATABASE_URL` del `.env` del propietario.

**Nota importante:** esa URL apunta a un proyecto **Supabase remoto**, no al
Postgres local de Docker — se descubrió durante esta verificación (se asumió
inicialmente que era local). Se confirmó explícitamente con el propietario
que la migración (puramente aditiva: `ADD COLUMN IF NOT EXISTS`,
`CREATE INDEX IF NOT EXISTS`, sin tocar filas existentes) se queda aplicada
en ese entorno. No se escribió ningún dato de prueba contra esa base — el
intento de verificación end-to-end con datos reales se abortó al descubrir
que apuntaba a Supabase (el script se quedó bloqueado por red/latencia y se
canceló antes de insertar nada) y la verificación funcional real se hizo en
su lugar contra la base de test local (`ancoramind_test`, Docker) mediante
`pytest tests/integration/`.

Pendiente para el propietario (no bloqueante, mismo patrón que specs/010
§T6 "pendiente de hacer con el propietario"):

- [ ] Confirmar en Supabase que las columnas/índices de `0007_recurrence_snooze`
      existen como se espera (`\d ancora.calendar_events`, `\d ancora.reminders`).
- [ ] Validación E2E real por Telegram: crear un evento `yearly` con
      `with_reminder=True`, confirmar que aparece cada año en `check_calendar`
      y que el recordatorio vinculado llega; forzar el disparo de un
      recordatorio recurrente y confirmar la nueva ocurrencia `pending`;
      probar `propose_reminder_snooze`/`execute_reminder_snooze` de extremo
      a extremo.

## Success Criteria (spec.md) — estado

1. ✅ Evento `yearly` con fecha pasada aparece en `check_calendar` del año en
   curso sin fila nueva — cubierto por test de servicio
   (`test_past_anchor_yields_occurrence_in_current_range`) y por integración.
2. ✅ `propose_calendar_event(..., with_reminder=True)` confirmado crea
   evento + recordatorio vinculado con la misma regla — cubierto por
   `test_execute_creates_event_and_linked_reminder`.
3. ✅ Recordatorio recurrente disparado queda `fired` con `fired_at`, crea la
   siguiente ocurrencia `pending` con `recurrence_parent_id` a la raíz; no
   crea nada si supera `until` — cubierto en `test_reminder_worker.py`.
4. ✅ Snooze confirmado crea una fila `pending` en `ahora + N horas` sin
   recurrencia propia — cubierto en servicio y en tools.
5. ✅ `delete_old_fired` purga solo filas `fired` con `fired_at` anterior al
   corte — cubierto por el repositorio y ejercitado en el worker cada ciclo.
6. ✅ `pytest`/`ruff`/`mypy` verdes.
7. ✅ `AGENTS.md`/`BACKLOG.md` referencian BL-41/specs/024.
