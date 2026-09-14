# AncoraMind — Despliegue en Railway

> **Propósito:** desplegar AncoraMind fuera del equipo local con un dominio HTTPS
> estable para Telegram, Supabase como PostgreSQL/Storage y CI/CD desde GitHub.
> No usar ngrok en este flujo.

> **Estado BL-23 (2026-09-14):** el código de OpenTelemetry metadata-only y el
> manifiesto del Collector están implementados y validados localmente. LiteLLM,
> PostgreSQL dedicado del Gateway y el despliegue real del Collector/Grafana en
> Railway siguen pendientes de un rollout explícito. Los runbooks operativos
> están en `docs/runbooks-013.md` (T13); E2E, rotación real, dashboards y
> benchmark con clave real son checklist pendiente, no parte de T13.

## Arquitectura de producción

```text
Telegram ── HTTPS webhook ──> Railway (AncoraMind / AgentOS)
                                     ├── Supabase PostgreSQL
                                     ├── Supabase Storage
                                     └── proveedor LLM
```

Target aprobado, pendiente de implementación:

```text
Telegram → AncoraMind admission → Agno → LiteLLM privado → OpenRouter
                                      └→ OTel Collector → Grafana Cloud
```

LiteLLM y el Collector se comunicarán por private networking de Railway y no
tendrán dominio público. La caída de LiteLLM será fail closed; la caída del
Collector/Grafana será fail open respecto a la funcionalidad.

El dominio Railway permanece estable entre deployments. El webhook se registra
una vez contra `https://<service>.up.railway.app/telegram/webhook`, no en cada
commit.

## 1. Antes de crear el servicio

1. Confirma que la rama `main` contiene un workflow CI verde en GitHub.
2. No copies `.env` al repositorio ni al Docker image. Las variables se cargan
   exclusivamente en Railway → **Variables**.
3. Mantén Supabase como infraestructura canónica. No añadas una base de datos
   Railway para datos `ancora` ni ejecutes DDL desde Railway: el baseline ya está
   aplicado. La futura DB Railway de LiteLLM será infraestructura separada y
   sustituible, sin acceso al schema canónico.
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

# T4 durable admission is implemented but deliberately disabled until T5
# connects the processor/Agent claim. Do not enable it in production yet.
TELEGRAM_ADMISSION_ENABLED=false
# Required together when the controlled rollout enables admission:
# TELEGRAM_BOT_ID=<numeric-getMe-id>
# TELEGRAM_PAYLOAD_ENCRYPTION_KEY=<fernet-key>
# TELEGRAM_PAYLOAD_KEY_VERSION=1
# TELEGRAM_ADMISSION_USER_BURST=5
# TELEGRAM_ADMISSION_BURST_WINDOW_SECONDS=10
# TELEGRAM_ADMISSION_USER_REQUESTS_PER_MINUTE=10
# TELEGRAM_ADMISSION_USER_REQUESTS_PER_HOUR=120
# TELEGRAM_ADMISSION_PENDING_GLOBAL=20
# TELEGRAM_ADMISSION_QUEUED_PER_CHAT=5

# T5 processor is implemented but disabled until a controlled T4+T5 rollout.
TELEGRAM_PROCESSOR_ENABLED=false
# TELEGRAM_PROCESSOR_POLL_INTERVAL_SECONDS=1.0
# TELEGRAM_PROCESSOR_GLOBAL_CONCURRENCY=2

# T6 runtime-config control plane is implemented but must remain disabled in
# production until a controlled admin rollout is explicitly approved.
RUNTIME_CONFIG_ADMIN_ENABLED=false
# Keep RUNTIME_CONFIG_ADMIN_TOKEN only as a Railway secret; never in Git/logs.
# RUNTIME_CONFIG_ADMIN_TOKEN=
# Logical route used before PostgreSQL initialization succeeds. It must exist in
# the approved bootstrap configuration and contain no secrets.
# RUNTIME_CONFIG_BOOTSTRAP_DEFAULT_ROUTE=ancoramind-default

LLM_PROVIDER=<openai|openrouter|openai-like>
LLM_MODEL=<modelo-elegido>
OPENAI_API_KEY=<si-aplica>
OPENROUTER_API_KEY=<si-aplica>
LLM_BASE_URL=<solo-openai-like>

# T10: la aplicación y Docker fuerzan AGNO_TELEMETRY=false. No habilitar
# tracing/telemetry propio de Agno: AncoraMind exporta sólo metadata allowlisted.
OBSERVABILITY_JSON_LOGS=true
# Tras crear el servicio privado Collector (sección 3.1), usar únicamente su
# hostname privado de Railway, sin dominio público ni Grafana directo.
# OTEL_EXPORTER_OTLP_ENDPOINT=http://ancoramind-otel-collector.railway.internal:4317
# OTEL_EXPORTER_OTLP_INSECURE=true
# OTEL_EXPORTER_OTLP_TIMEOUT_SECONDS=3
# OTEL_EXPORT_INTERVAL_MILLIS=30000

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

No añadas variables de LiteLLM a producción hasta completar el rollout de la
sección 3.2. Las variables OTLP se añaden únicamente al servicio AncoraMind
después de crear y validar el Collector privado descrito a continuación; nunca
apuntan directamente a Grafana Cloud.

### 3.1 Collector OpenTelemetry privado (T10)

1. Railway → **New Service** → **Docker Image**:
   `otel/opentelemetry-collector-contrib:0.138.0`.
2. Sube el fichero versionado `observability/otel-collector.yaml` como config del
   servicio y usa como comando:

   ```text
   --config=/etc/otelcol/config.yaml
   ```

3. No generes dominio público ni TCP proxy. El receptor gRPC `4317` se consume
   exclusivamente por private networking de Railway.
4. En el servicio Collector, define **solo como Railway secrets**:

   ```env
   GRAFANA_OTLP_ENDPOINT=<endpoint-otlp-http-grafana-cloud>
   GRAFANA_OTLP_AUTHORIZATION=Basic <token-grafana-cloud>
   ```

5. En el servicio AncoraMind, define `OTEL_EXPORTER_OTLP_ENDPOINT` con el host
   privado del Collector y las variables OTLP comentadas arriba. No copies los
   secretos de Grafana al servicio AncoraMind.
6. Valida primero que la app sigue respondiendo a `/health` con Collector apagado
   o con endpoint inaccesible: el pipeline es **fail-open**. Después revisa que
   Grafana recibe sólo atributos allowlisted: rutas, status, error class, tokens,
   coste, latencia y correlación; nunca prompts, mensajes, respuestas, documentos
   ni argumentos/resultados de tools.

El Collector aplica defensa en profundidad: `memory_limiter`, redacción de claves
de contenido conocidas, `batch` y cola/retry acotados antes del exporter Grafana.
El fichero se valida en CI/local con la imagen fijada `0.138.0` y valores dummy;
esa validación no contacta Grafana.

### 3.2 LiteLLM Gateway privado (T11)

El pilot está implementado y validado localmente (`gateway/`). El rollout Railway
crea dos servicios nuevos y tiene coste; ejecútalo solo con aprobación explícita:

1. **PostgreSQL dedicado del Gateway** — Railway → **New** → **Database** →
   **Add PostgreSQL**. Nómbralo p. ej. `litellm-db`. No compartas la BD canónica
   `ancora` ni la de `agno_runtime`: la DB de LiteLLM es infraestructura
   sustituible (virtual keys, spend logs, config).
2. **Servicio LiteLLM** — Railway → **New Service** → **GitHub Repo** apuntando
   a este repositorio con **root directory** `gateway/` (usa `gateway/Dockerfile`,
   imagen fijada por digest `ghcr.io/berriai/litellm@sha256:a3715fa7…c62bf`).
   No generes dominio público ni TCP proxy: el `4000` se consume por private
   networking (`http://<servicio>.railway.internal:4000`).
3. Variables del servicio LiteLLM (todas secretos):

   ```env
   DATABASE_URL=${{litellm-db.DATABASE_URL}}
   LITELLM_MASTER_KEY=<sk-master-aleatorio>
   LITELLM_SALT_KEY=<sk-salt-aleatorio-no-rotable>
   OPENROUTER_API_KEY=<clave-real-openrouter>
   NO_DOCS=True
   NO_REDOC=True
   NO_OPENAPI=True
   ```

   `LITELLM_SALT_KEY` cifra credenciales en la BD y no puede rotarse después de
   añadir modelos: genérala una vez y guárdala solo en Railway.
4. Espera deployment **SUCCESS** y valida desde tu terminal:

   ```powershell
   curl http://<servicio>.railway.internal:4000/health/readiness   # desde Railway shell/agent
   ```

   `/docs`, `/redoc` y `/openapi.json` deben devolver 404.
5. Crea la virtual key exclusiva de AncoraMind (restringida a los tres aliases,
   con límites RPM/TPM/max-parallel T12):

   ```powershell
   $env:LITELLM_PROXY_ADMIN_URL='http://<servicio>.railway.internal:4000'
   $env:LITELLM_MASTER_KEY='<sk-master>'
   $env:LITELLM_VIRTUAL_KEY_RPM='60'
   $env:LITELLM_VIRTUAL_KEY_TPM='250000'
   $env:LITELLM_VIRTUAL_KEY_MAX_PARALLEL_REQUESTS='4'
   # Opcional: backstop USD en el propio Gateway (rotación 30d)
   # $env:LITELLM_VIRTUAL_KEY_MAX_BUDGET_USD='<external_hard_limit>'
   # $env:LITELLM_VIRTUAL_KEY_BUDGET_DURATION='30d'
   python scripts/litellm_create_virtual_key.py
   ```

   La key se imprime una sola vez; guárdala como secreto
   `LITELLM_PROXY_VIRTUAL_KEY` del servicio AncoraMind. Nunca en Git/logs ni en
   revisiones runtime.

   **Circuit breaker (T12):** `gateway/litellm-config.yaml` declara
   `allowed_fails: 3` + `cooldown_time: 60` (igual a `gateway.cooldown_seconds`
   del runtime config); un deployment con fallos repetidos entra en cooldown y
   el proxy fast-faila sin llamar al upstream afectado (transición automática
   OPEN→HALF_OPEN→CLOSED).
6. En el servicio AncoraMind, activa el modo Gateway (fail-closed; sin estas
   variables la app no arranca en ese modo):

   ```env
   LITELLM_PROXY_ENABLED=true
   LITELLM_PROXY_BASE_URL=http://<servicio-litellm>.railway.internal:4000
   LITELLM_PROXY_VIRTUAL_KEY=<sk-virtual-key>
   LITELLM_PROXY_DEFAULT_ROUTE=ancoramind-default-r1
   ```

   Con el modo activo, la app deja de usar `OPENROUTER_API_KEY`/
   `OPENAI_API_KEY`; puedes retirarlas del servicio AncoraMind (quedan sólo en
   LiteLLM). Un Gateway caído ⇒ error de inferencia, nunca fallback directo.
7. Valida con un update de prueba que la respuesta llega y que
   `ancora.llm_usage_events` registra `provider=litellm`-vía-Gateway; después
   ejecuta el benchmark p50/p95/p99+TTFT frente a OpenRouter directo (T11,
   con clave real) antes de declarar el pilot cerrado.

8. **Cost governance (T12):** activa en una revisión runtime `cost_governance`
   (`external_hard_limit_usd` = hard limit OpenRouter al 100%,
   `daily_budget_usd`, `monthly_budget_usd`, `route_monthly_budgets_usd`
   opcional, umbrales 60/80/90%) junto con `pricing` y
   `max_estimated_cost_usd` por interacción (invariante: rutas de pago exigen
   las tres). El runner evalúa el spend al inicio de cada run: alertas 60/80%
   en telemetría, hard stop al 90% (`failed_controlled`, sin replay).
   Reconcilia con `GET https://openrouter.ai/api/v1/key`
   (`limit`/`limit_remaining`, usage diario/semanal/mensual) antes de subir
   los techos.

Validación local sin Railway (sin coste, claves dummy):

```powershell
$env:LITELLM_MASTER_KEY='sk-local-master'; $env:LITELLM_SALT_KEY='sk-local-salt'
$env:OPENROUTER_API_KEY='dummy'
docker compose -p ancoramind-litellm -f gateway/docker-compose.litellm.yml up -d --build
# readiness/docs/aliases/key: ver specs/013 verification T11
docker compose -p ancoramind-litellm -f gateway/docker-compose.litellm.yml down -v
```

> **Rollout T4/T5:** cuando se active `TELEGRAM_ADMISSION_ENABLED=true`, el
> endpoint estable `/telegram/webhook` pasa a ser propiedad de AncoraMind y
> requiere `ANCORA_DATABASE_URL`, `TELEGRAM_BOT_ID`, secret Telegram, clave
> Fernet y una allowlist no vacía. T4 persiste/deduplica/rechaza de forma durable;
> no activarlo en producción hasta que T5 procese de forma segura las filas
> `accepted`.

> **T5:** el processor implementado reclama `accepted`, persiste una outbox
> cifrada y entrega chunks con estado durable. Antes de activar ambos flags en
> Railway, ejecutar el runbook de rollout: comprobar migración `head`, secret,
> bot ID, allowlist, backlog `accepted=0`, una réplica y logs; después validar un
> único update de prueba. No activar T5 con T4 apagado.
>
> **T6:** el control plane runtime implementado crea/activa revisiones tipadas e
> inmutables, cachea un snapshot in-memory para futuros runs y audita cada cambio
> con actor/motivo. Mantener `RUNTIME_CONFIG_ADMIN_ENABLED=false` en producción
> hasta aprobar un rollout administrativo controlado. El token viaja únicamente en
> `Authorization: Bearer` y `RUNTIME_CONFIG_ADMIN_TOKEN` vive solo en Railway
> secrets; no aceptar secrets en revisiones ni habilitar CORS.

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
