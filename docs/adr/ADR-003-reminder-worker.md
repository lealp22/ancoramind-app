# ADR-003 — Worker de recordatorios en el proceso de la app

> **Status:** Accepted (implementado 2026-09-09 — specs/010, BL-5)
> **Contexto:** BL-5. Mini-ADR solicitado por el backlog para fijar la decisión.

---

## Contexto

Los recordatorios se crean con status `pending` tras confirmación humana
(`propose_reminder` → "Sí" → `execute_reminder`) pero nada los dispara. Hace
falta un mecanismo que periódicamente detecte los vencidos (`trigger_at <=
now`), notifique al usuario y marque `fired`.

Restricciones relevantes:

- **BL-18 en pausa**: sin canal webhook autorizado (ngrok vetado; Railway
  pendiente de la parte operativa).
- **ADR-001**: Agno es infraestructura reemplazable — no acoplar el disparo a
  internals de AgentOS/Agno.
- **§2.7**: la memoria canónica vive en PostgreSQL (Supabase, ADR-002); el
  worker es un consumidor más del schema `ancora`.
- **§2.8**: el contenido del recordatorio (título/detalle) es DATA no
  confiable — no puede romper la entrega ni inyectar formato.

## Decisión

**Worker asyncio dentro del proceso de la app** (mismo servicio Railway, sin
procesos/servicios extra):

1. **Bucle** — `RemindersWorker.run_forever(interval)` como `asyncio.Task`
   arrancado en el startup de FastAPI (`app.add_event_handler`) y cancelado en
   el shutdown. Intervalo configurable (`REMINDER_POLL_INTERVAL_SECONDS`,
   default 60 s).
2. **Dominio puro** — `src/domain/reminders/worker.py` conoce el repositorio y
   un Protocol `ReminderNotifier`; no importa nada de Agno ni de Telegram.
3. **Notificación outbound** — `TelegramNotifier` (`src/notifications/`)
   llama a la Bot API `sendMessage` con httpx (texto plano, sin `parse_mode`,
   `chat_id` = user id de Telegram, válido en private chats). **No requiere
   webhook ni túnel**: la entrega puede validarse antes de cerrar BL-18.
4. **Persistencia** — `list_due()` + `mark_fired()` en `RemindersRepository`;
   `mark_fired` solo actúa sobre `status='pending'` (idempotente). La entrega
   fallida deja el recordatorio `pending` → reintento en el ciclo siguiente.
5. **Auto-gates** — el worker solo arranca con `ANCORA_DATABASE_URL` +
   `TELEGRAM_TOKEN` (+ `REMINDER_WORKER_ENABLED`, default true), con log del
   motivo cuando no arranca (degradación graceful, igual que domain tools).

### Gobernanza (§7 docs/governance.md)

Disparar un recordatorio **no es una acción WRITE nueva**: es la ejecución
diferida de una acción ya confirmada por el usuario al crearla. El worker no
crea entidades ni expande permisos; la transición interna `pending→fired` no
requiere ActionProposal. La auditoría de origen se conserva
(`source_document_id` / `source_action_id`).

## Relación con BL-18 (Railway) — operativa

- **Mismo servicio**: el worker arranca con la app (CMD del `Dockerfile`);
  no hay servicio ni cron de Railway aparte. Al activar Railway (BL-18),
  cargar `REMINDER_WORKER_ENABLED`/`REMINDER_POLL_INTERVAL_SECONDS` si se
  quieren valores no-default (funciona con defaults).
- **Huecos de cobertura**: deploys, restarts y healthchecks dejan periodos sin
  worker. Como los recordatorios son duraderos en BD, al arrancar se disparan
  los vencidos durante el hueco, con nota de retraso si supera 5 min.
- **Réplica única**: Railway corre 1 réplica por defecto. Con escalado
  horizontal (>1 réplica) podría notificarse dos veces (TOCTOU entre
  `list_due` y `mark_fired`) — fuera de POC; documentado aquí.
- **Supabase free tier pausado**: el ciclo falla (log) y reintenta en el
  siguiente intervalo; al restaurar, se disparan los vencidos acumulados.
- **Validación sin BL-18**: basta con la app corriendo (local o Railway) con
  un recordatorio `pending` vencido en la BD → recibirá el mensaje saliente
  sin necesidad del webhook inbound.

## Limitaciones aceptadas

- **Sin `fired_at`/`attempts` en schema**: no hay columna de disparo real ni
  contador de reintentos (el schema actual no las tiene y Alembic es BL-12).
  Si la entrega falla indefinidamente, el recordatorio reintenta cada ciclo
  para siempre → un reintento máximo/dead-letter se diseñará con la migración.
- **Un solo canal** (Telegram). Otros canales requieren otro `ReminderNotifier`
  del mismo Protocol.
- **`dismissed` sin tool**: el estado existe en el modelo pero no hay capability
  para que el usuario cancele un recordatorio (backlog futuro).

## Alternativas consideradas

| Alternativa | Por qué no |
|---|---|
| APScheduler | Dependencia extra para lo que un `while True: sleep` resuelve en el POC; su ventaja (cron expressions, jobstore) no aporta aquí |
| Cron externo / Railway Cron Job | Servicio separado, duplicación de configuración y de ciclo de despliegue; razonable si el worker crece (ver re-evaluación) |
| Dejarlo en Agno/AgentOS | Acopla el disparo al runtime reemplazable (ADR-001) y a sus internals |
| Webhook con `sendMessage` reactivo (sin worker) | Requiere que el usuario escriba para descubrir vencidos; no cumple "avísame" |

## Re-evaluación

Reabrir si: (a) se escala a >1 réplica → necesita advisory lock o UPDATE
`WHERE ... RETURNING` como claim atómico; (b) aparece `fired_at` con BL-12 →
añadir backoff/dead-letter; (c) el volumen de recordatorios hace el polling
inviable → pub/sub o scheduler externo; (d) se añaden canales (WhatsApp, email)
→ el Protocol ya lo soporta, solo implementar notifiers.
