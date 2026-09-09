# AncoraMind — Despliegue en Railway

> **Propósito:** desplegar AncoraMind fuera del equipo local con un dominio HTTPS
> estable para Telegram, Supabase como PostgreSQL/Storage y CI/CD desde GitHub.
> No usar ngrok en este flujo.

## Arquitectura de producción

```text
Telegram ── HTTPS webhook ──> Railway (AncoraMind / AgentOS)
                                     ├── Supabase PostgreSQL
                                     ├── Supabase Storage
                                     └── proveedor LLM
```

El dominio Railway permanece estable entre deployments. El webhook se registra
una vez contra `https://<service>.up.railway.app/telegram/webhook`, no en cada
commit.

## 1. Antes de crear el servicio

1. Confirma que la rama `main` contiene un workflow CI verde en GitHub.
2. No copies `.env` al repositorio ni al Docker image. Las variables se cargan
   exclusivamente en Railway → **Variables**.
3. Mantén Supabase como infraestructura canónica. No añadas una base de datos
   Railway ni ejecutes DDL desde Railway: `ancora_baseline` ya está aplicado.
4. Genera un secret aleatorio para `TELEGRAM_WEBHOOK_SECRET_TOKEN`:

   ```powershell
   python -c "import secrets; print(secrets.token_urlsafe(32))"
   ```

## 2. Crear servicio Railway desde GitHub

1. Railway → **New Project** → **Deploy from GitHub repo**.
2. Conecta el repositorio `lealp22/ancoramind-app` y selecciona el servicio.
3. Railway detectará `railway.json` y construirá el `Dockerfile`.
4. En **Settings → Networking**, genera un dominio Railway. Anota únicamente
   la URL pública; no necesitas ngrok.
5. En **Settings → Source**, selecciona la rama `main`, habilita **Auto Deploy**
   y **Wait for CI**.
6. En **Settings → Healthcheck**, confirma que Railway usa `/health` y espera
   hasta 300 segundos. Está declarado en `railway.json`.

## 3. Variables de producción

En Railway → **Variables**, añade los secretos. Nunca los pegues en Git, logs o
capturas de pantalla:

```env
APP_ENV=production
LOG_LEVEL=INFO
APP_DEBUG=false

TELEGRAM_TOKEN=<bot-production-token>
TELEGRAM_WEBHOOK_SECRET_TOKEN=<secret-aleatorio>
ALLOWED_TELEGRAM_USER_IDS=452022640

LLM_PROVIDER=<openai|openrouter|openai-like>
LLM_MODEL=<modelo-elegido>
OPENAI_API_KEY=<si-aplica>
OPENROUTER_API_KEY=<si-aplica>
LLM_BASE_URL=<solo-openai-like>

AGNO_DATABASE_URL=postgresql+psycopg://<session-pooler>
ANCORA_DATABASE_URL=postgresql+asyncpg://<session-pooler>

DOCUMENT_STORAGE_BACKEND=supabase
SUPABASE_URL=https://<project-ref>.supabase.co
SUPABASE_SERVICE_ROLE_KEY=<server-side-only>
SUPABASE_STORAGE_BUCKET=ancora-documents

# Reminder worker (BL-5 / ADR-003) — optional; defaults shown work as-is.
# Auto-gated: needs ANCORA_DATABASE_URL + TELEGRAM_TOKEN (already above).
# Outbound only: fires pending reminders without depending on the webhook.
REMINDER_WORKER_ENABLED=true
REMINDER_POLL_INTERVAL_SECONDS=60
```

No configures `NGROK_URL`. Railway proporciona `PORT` automáticamente; la app
lo consume en producción y escucha en `0.0.0.0` sin autoreload.

## 4. Primer deployment y healthcheck

Espera a que el deployment esté **SUCCESS**. En los logs debe aparecer:

```text
Starting HTTP server — host: 0.0.0.0 | port: <PORT> | reload: False
```

Comprueba desde tu terminal:

```powershell
Invoke-RestMethod https://<service>.up.railway.app/health
```

La respuesta debe incluir `status: ok`. Si `/health` no devuelve `2xx`, Railway
no activa la nueva versión.

## 5. Registrar webhook de Telegram

Tras un deployment saludable, desde una terminal local con `.env` que contenga
el mismo `TELEGRAM_TOKEN` y `TELEGRAM_WEBHOOK_SECRET_TOKEN`:

```powershell
python scripts/telegram_webhook.py set `
  --base-url https://<service>.up.railway.app

python scripts/telegram_webhook.py status
```

El script no muestra tokens ni el secret. Para desactivar el canal:

```powershell
python scripts/telegram_webhook.py delete

# Solo si aceptas descartar mensajes acumulados:
python scripts/telegram_webhook.py delete --drop-pending-updates
```

## 6. Ciclo de cambios

```text
feature branch → Pull Request → CI verde → merge main
→ Railway espera CI → build → healthcheck → deployment activo
```

- Si CI falla, Railway omite el deployment cuando **Wait for CI** está activo.
- Si el proceso no arranca o `/health` falla, Railway no conmuta tráfico a la
  nueva versión.
- Si detectas un fallo funcional tras desplegar, usa el rollback al deployment
  anterior desde Railway; después corrige el código en una nueva rama.

## 7. Staging futuro

No conectes staging y production con el mismo bot: Telegram permite un único
webhook por `TELEGRAM_TOKEN`. Un entorno staging requerirá:

- segundo bot/token;
- `TELEGRAM_WEBHOOK_SECRET_TOKEN` distinto;
- idealmente proyecto Supabase separado antes de usar datos reales;
- dominio Railway distinto.

Hasta entonces se recomienda un único entorno production protegido por
`ALLOWED_TELEGRAM_USER_IDS`, más Pull Requests y CI antes de mergear.

## 8. Recordatorios: worker interno (BL-5 / ADR-003)

El worker de recordatorios corre **dentro del mismo servicio** que la app
(arranca con FastAPI en el startup). No requiere ningún servicio o cron de
Railway aparte, ni configuración adicional si aceptas los defaults
(`REMINDER_WORKER_ENABLED=true`, `REMINDER_POLL_INTERVAL_SECONDS=60`).

Comportamiento esperado en Railway:

- **El disparo es outbound** (`sendMessage` de la Bot API): funciona aunque el
  webhook inbound aún no esté registrado. El worker se activa con el primer
  deployment saludable — antes incluso de completar el paso 5 (webhook).
- **Deploys y restarts**: durante un deploy el worker está parado. Los
  recordatorios vencidos en ese hueco quedan `pending` (son duraderos en la
  BD de Supabase) y se disparan al arrancar la nueva versión, con nota de
  retraso si superan 5 min.
- **Réplica única**: Railway corre una réplica por defecto — no escalar
  horizontalmente sin resolver el doble disparo (TOCTOU, ver ADR-003).
- **Supabase free tier pausado**: los ciclos fallarán con error en los logs y
  se reintentan cada intervalo; al restaurar el proyecto se disparan los
  vencidos acumulados.

Validación post-deployment (sin webhook): crea un recordatorio con `trigger_at`
en el futuro cercano (o deja uno vencido en la BD); en los logs debe aparecer
`Reminder worker started` y el mensaje debe llegar al chat privado del bot.

## Troubleshooting

| Síntoma | Acción |
|---|---|
| Deployment falla al arrancar | Revisar logs y variables; confirmar URLs pooler Supabase y proveedor LLM. |
| Healthcheck falla | Confirmar que Railway inyecta `PORT` y que `/health` devuelve `status: ok`. |
| Telegram no entrega mensajes | Ejecutar `python scripts/telegram_webhook.py status`; confirmar dominio, secret y `TELEGRAM_TOKEN`. |
| CI verde pero no hay deploy | Confirmar en Railway que el servicio observa `main`, Auto Deploy y Wait for CI están activos. |
| Recordatorios no llegan | Revisar logs: debe aparecer `Reminder worker started (interval=…s)`. Confirmar `TELEGRAM_TOKEN`, `ANCORA_DATABASE_URL`, `REMINDER_WORKER_ENABLED` y que el recordatorio sigue `pending` con `trigger_at` vencido. Nota: el disparo es outbound — no depende del webhook. |
| Necesitas volver atrás | Railway → deployment anterior → Rollback; no cambies el webhook si el dominio no cambió. |