# Spec: 010 — Reminder Background Worker

> **Backlog:** BL-5
> **Status:** implemented (2026-09-09) — ver `verification.md`
> **Decisiones:** docs/adr/ADR-003-reminder-worker.md
> **Target:** Disparar los recordatorios `pending` cuyo `trigger_at` ha vencido
> y notificar al usuario por Telegram — sin depender del canal webhook (BL-18).

---

## Requirement

Los recordatorios se crean con status `pending` (tras confirmación
propose/execute) pero nada los dispara. Hace falta un proceso que periódicamente
busque los vencidos, notifique al usuario y los marque `fired`.

**Relación con BL-18 (Railway):** el worker vive en el mismo proceso que la app
(un único servicio Railway, mismo `Dockerfile`/CMD, sin servicio extra). La
notificación es **outbound** (`sendMessage` de la Bot API): NO requiere webhook
HTTPS ni túnel — puede validarse antes de cerrar BL-18. Los envíos dependen solo
de `TELEGRAM_TOKEN` y de que el proceso esté vivo; los recordatorios son
**duraderos en BD**: si el servicio está parado (deploy, restart, Supabase
pausado), quedan `pending` y se disparan al arrancar (tardíos).

### Must Have

- `RemindersWorker` (domain): `run_once()` que lista vencidos → notifica →
  marca `fired` solo si la entrega tuvo éxito; `run_forever(interval)` con
  tolerancia a errores por ciclo y cancelación limpia.
- `ReminderNotifier` Protocol (inversión): domain no conoce Telegram.
- `TelegramNotifier` (`src/notifications/telegram.py`): `sendMessage` vía
  httpx, texto plano (sin `parse_mode` — contenido no confiable, §2.8),
  validación de `chat_id` numérico (private chats: user_id == chat id).
- `RemindersRepository.list_due(now, limit)` y `mark_fired(id, user_id)`
  (`WHERE status='pending'` — idempotente ante reintentos).
- Wiring en `main.py` con FastAPI startup/shutdown handlers y auto-gates:
  `REMINDER_WORKER_ENABLED` (default true) + `ANCORA_DATABASE_URL` +
  `TELEGRAM_TOKEN`; intervalo `REMINDER_POLL_INTERVAL_SECONDS` (default 60).
- Mensaje con nota de retraso si el disparo llega >5 min tarde.
- Tests: unit (worker + notifier con mocks/httpx MockTransport, incluida
  cancelación del loop) e integration (ciclo real contra PostgreSQL).

### Should Have

- Log del worker observable en Railway (qué se disparó, fallos de entrega).
- Documentación de operación Railway: variables, huecos en deploys, réplica
  única (TOCTOU), disparo tardío, `fired_at` pendiente de BL-12.

### Won't Have (esta spec)

- Cambios de schema (`fired_at`, `attempts`): requieren Alembic (BL-12).
- Reintentos con backoff ni dead-letter: si la entrega falla, el recordatorio
  queda `pending` y se reintenta en el siguiente ciclo (POC).
- Railway Cron Job como servicio separado: alternativa documentada en ADR-003,
  no necesaria para el POC (un solo proceso).
- Dismiss por usuario (status `dismissed` ya existe en modelo pero no hay tool;
  es una capability futura).
- Notificación por canales distintos de Telegram.

---

## Design

```text
FastAPI startup (main.py, auto-gated)
  └── asyncio.create_task(RemindersWorker.run_forever(interval))
        └── per cycle: run_once()
              ├── RemindersRepository.list_due(now)   [pending & trigger_at <= now]
              ├── por cada vencido: notifier.send_reminder(reminder)
              │     ├── ok  → repo.mark_fired(id, user_id)   [WHERE status='pending']
              │     └── fail → queda pending (log warning; reintento próximo ciclo)
              └── finally: session.close()
```

- **Gobernanza:** disparar es la ejecución diferida de una acción ya confirmada
  (`propose_reminder` → usuario "Sí" → `execute_reminder`). El worker no crea
  entidades nuevas ni expande permisos: transición interna `pending→fired`.
- **Escalado:** réplica única (Railway default). Con >1 réplica podría
  notificarse dos veces (TOCTOU entre list y mark); documentado, fuera de POC.
- **Dominio puro:** worker importa repo y Protocol; Telegram vive en
  `src/notifications/` (wiring en main). Sin imports de Agno en el flujo.

## Success Criteria

1. Recordatorio vencido → notificado por Telegram → status `fired` (integration
   test verde contra PostgreSQL real).
2. Fallo de entrega → queda `pending` y se reintenta en el siguiente ciclo.
3. Errores de un ciclo no matan el loop; cancelación (shutdown) es limpia.
4. Sin `ANCORA_DATABASE_URL` o sin `TELEGRAM_TOKEN` el worker no arranca y se
   loguea el motivo (degradación graceful, igual que las domain tools).
5. Unit + integration suites verdes; Ruff limpio.
6. ADR-003 + docs (development, deployment-railway, .env.example, AGENTS,
   BACKLOG) actualizados con la relación BL-18 explícita.
