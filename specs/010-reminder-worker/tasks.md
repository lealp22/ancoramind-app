# Tasks: 010 — Reminder Background Worker

## T1: Repository

- [x] `RemindersRepository.list_due(now, limit=50)` — `status='pending' AND
      trigger_at <= :now ORDER BY trigger_at LIMIT :limit`.
- [x] `RemindersRepository.mark_fired(id, user_id) -> bool` — UPDATE con
      `WHERE status='pending'` (idempotente para reintentos/reescala).

## T2: Domain worker

- [x] `src/domain/reminders/worker.py`: Protocol `ReminderNotifier`
      (`send_reminder(reminder) -> bool`) + `RemindersWorker`
      (session_factory + notifier inyectados).
- [x] `run_once()`: list_due → notificar → mark_fired solo con entrega OK;
      `finally: session.close()`; devuelve nº disparados. Mejora durante la
      implementación: excepción de UN recordatorio no aborta el lote (log +
      siguiente), y no marca fired.
- [x] `run_forever(interval)`: errores por ciclo no matan el loop
      (log + continuar); `asyncio.CancelledError` se propaga limpio.

## T3: Telegram notifier

- [x] `src/notifications/telegram.py`: `TelegramNotifier` (httpx AsyncClient,
      `sendMessage` texto plano sin `parse_mode`), `format_reminder_message`
      (título, detalle, fecha programada, nota de retraso >5 min), chat_id
      numérico (private chat == user_id) o fail-safe log.
- [x] `src/notifications/__init__.py`.

## T4: Config + wiring

- [x] `Settings`: `reminder_worker_enabled: bool = True`,
      `reminder_poll_interval_seconds: int = 60`.
- [x] `main.py`: `_register_reminder_worker(app, settings)` con FastAPI
      startup/shutdown handlers; auto-gates + logs de motivo si no arranca.
- [x] `.env.example` + `docs/development.md` (env vars + sección Run) +
      `docs/deployment-railway.md` (variables + §8 operación + troubleshooting).

## T5: Tests

- [x] Unit worker: dispara vencidos, deja pending si falla entrega, continúa
      tras excepción del notifier (y del ciclo), 0 si no hay vencidos,
      cancelación limpia del loop con error previo.
- [x] Unit notifier: formato (título/detalle/fecha/retraso), chat_id no
      numérico sin llamada HTTP, éxito y fallo HTTP vía `httpx.MockTransport`,
      sin `parse_mode` en el body.
- [x] Integration: vencido → fired + notificado; futuro queda pending;
      segundo ciclo no re-notifica (idempotencia real en BD).

## T6: Docs + verificación

- [x] `docs/adr/ADR-003-reminder-worker.md` (decisión, alternativas, relación
      BL-18/Railway, limitaciones, gobernanza).
- [x] AGENTS.md (tree, estado, ADR-003) + BACKLOG.md (cerrar BL-5 → Hecho +
      nota en BL-18).
- [ ] Validación E2E de entrega real (con recordatorio vencido en Supabase y
      la app corriendo): **pendiente de hacer con el propietario** — no
      requiere webhook; ver `verification.md`.
- [x] `pytest` completo + Ruff verdes; `verification.md`.
