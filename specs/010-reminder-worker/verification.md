# Verification: 010 — Reminder Background Worker

> **Fecha:** 2026-09-09 · **Entorno:** Windows 11 + Docker Desktop 29.2.1
> (pgvector/pgvector:pg16) · **Estado:** ✅ verificado (E2E de entrega real
> pendiente de hacer con el propietario — ver abajo)

---

## Resultado

| Check | Resultado |
|---|---|
| `pytest` completo (unit + integration) | ✅ **156 passed** (139 unit + 17 integration) |
| Tests nuevos | ✅ 13 unit (5 worker + 8 notifier) + 1 integration |
| Integration: ciclo real contra PostgreSQL | ✅ vencido → notificado → `fired`; futuro queda `pending`; 2º ciclo no re-notifica (idempotencia en BD) |
| Cancelación limpia del loop (con error previo) | ✅ unit test: error de ciclo no mata el loop, cancel → `CancelledError` |
| `ruff check src/ tests/ scripts/` | ✅ limpio |
| Wiring sin requisitos | ✅ auto-gates (log de motivo, worker no arranca) — cubierto por diseño + logs |

## Qué se implementó

| Pieza | Fichero |
|---|---|
| `list_due()` / `mark_fired()` (idempotente sobre `status='pending'`) | `src/repositories/reminders.py` |
| `ReminderNotifier` Protocol + `RemindersWorker` (`run_once` / `run_forever`) | `src/domain/reminders/worker.py` |
| `TelegramNotifier` + `format_reminder_message` (texto plano, nota de retraso >5 min) | `src/notifications/telegram.py` |
| Config (`REMINDER_WORKER_ENABLED`, `REMINDER_POLL_INTERVAL_SECONDS`) | `src/config.py` |
| Startup/shutdown FastAPI con auto-gates | `src/main.py` (`_register_reminder_worker`) |
| Mini-ADR (decisión + relación BL-18 + limitaciones + gobernanza) | `docs/adr/ADR-003-reminder-worker.md` |

## Mejoras surgidas durante la implementación

1. **Excepción de un recordatorio no aborta el lote**: `run_once` captura
   errores por item (log + continuar); solo un fallo de ciclo completo (p. ej.
   BD caída) queda para `run_forever`, que reintenta en el siguiente intervalo.
2. **`mark_fired` con `WHERE status='pending'`** hace el disparo idempotente
   también ante un hipotético segundo worker (validado en integration).

## Relación con BL-18 (documentada en ADR-003 + deployment-railway §8)

- **El worker va dentro del servicio Railway** (arranca con la app): cero
  configuración extra; variables opcionales con defaults válidos.
- **La entrega es outbound** (`sendMessage`): no requiere el webhook inbound →
  **se puede validar antes de cerrar BL-18** (incluso en local con Supabase).
- **Huecos de deploy/restart**: los vencidos quedan `pending` (duraderos en BD)
  y se disparan al arrancar con nota de retraso >5 min.
- **Réplica única**: no escalar sin resolver TOCTOU (ADR-003, re-evaluación).
- **Sin `fired_at`/`attempts` en schema**: pendiente de BL-12 (Alembic).

## E2E pendiente de hacer con el propietario (sin webhook)

1. Arrancar la app local (`python -m src.main`) con `.env` de Supabase y
   `TELEGRAM_TOKEN` válido → logs: `Reminder worker started (interval=60s)`.
2. Pedirle al bot (o insertar) un recordatorio con `trigger_at` en 1-2 min.
3. Esperar el ciclo → debe llegar el mensaje al chat privado del bot y el
   recordatorio aparecer como `fired` con `list_reminders`.
4. En Railway (cuando BL-18 se cierre): misma comprobación tras el primer
   deployment saludable, **antes** de registrar el webhook (ver
   `docs/deployment-railway.md` §8).

## Limitaciones conocidas (heredadas del POC)

- Reintento infinito sin backoff si la entrega falla siempre (dead-letter
  cuando BL-12 añada `attempts`/`fired_at`).
- Un solo canal (Telegram); el Protocol soporta más notifiers.
- Status `dismissed` sin tool para cancelar recordatorios (backlog futuro).
