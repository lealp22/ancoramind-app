# AncoraMind — Local Development Guide

> Comandos multi-shell: los que usan `<` (redirección bash) no funcionan en
> PowerShell — se indica la alternativa cuando aplica.
> Para probar con Telegram real: ver [deployment-railway.md](deployment-railway.md)
> (único flujo vigente desde BL-18 — ngrok no se usa en este proyecto desde el
> incidente de seguridad del 2026-09-07). [quick-start.md](quick-start.md)
> cubre el día a día una vez el servicio Railway existe.
> [deployment-e2e.md](deployment-e2e.md) es la guía histórica de primera
> configuración, con un paso de ngrok ya no vigente — léela con esa salvedad.

## Prerequisites

- Python 3.12+
- Proyecto Supabase activo (opción principal) o Docker & Docker Compose
  (alternativa local)
- ngrok **no se usa** en este proyecto (incidente de seguridad 2026-09-07,
  BL-18). El dominio estable de Railway sustituye cualquier necesidad de
  túnel local.
- Credenciales en `.env` (ver [`.env.example`](../.env.example))

## Setup

```bash
# Clone
git clone <repo-url>
cd ancoramind-core

# Virtual environment
# PowerShell:
.venv/Scripts/Activate.ps1
# Git Bash:
source .venv/Scripts/activate

# Install dependencies (con el venv activado)
pip install -e ".[dev]"

# Environment
cp .env.example .env
# Editar .env con tus credenciales
```

## Database

### Opción principal: Supabase

Usar el **Session pooler** (IPv4, puerto 5432) del Dashboard → Connect:

```env
AGNO_DATABASE_URL=postgresql+psycopg://postgres.<ref>:<password>@<pooler>:5432/postgres
ANCORA_DATABASE_URL=postgresql+asyncpg://postgres.<ref>:<password>@<pooler>:5432/postgres
DOCUMENT_STORAGE_BACKEND=supabase
SUPABASE_URL=https://<ref>.supabase.co
SUPABASE_SERVICE_ROLE_KEY=<service-role-key>
SUPABASE_STORAGE_BUCKET=ancora-documents
```

No usar el Transaction pooler (6543) con la configuración actual de asyncpg.
La Service Role Key es exclusivamente server-side y nunca se commitea.

Las variables del proceso tienen prioridad sobre `.env`. Si cambias entre
Docker local y Supabase, abre una terminal nueva o recarga `.env`; de lo
contrario, una URL antigua exportada puede seguir apuntando a `localhost`.

### Ledger y admission Telegram (T3–T4 de specs/013)

El ledger durable tiene cifrado de payload recuperable. T4 añade un endpoint
propio `POST /telegram/webhook`, preservando la URL pública, y lo instala delante
de la ruta Telegram de AgentOS cuando `TELEGRAM_ADMISSION_ENABLED=true`.

El endpoint valida el secret, exige chat privado y allowlist, registra el
`X-Railway-Request-Id`, deduplica por `bot_id + update_id`, aplica límites
durables y devuelve `200` solo tras el commit. Un update duplicado no consume
cuota. Todavía no inicia Agno ni envía respuestas: T5 procesará después los
claims `accepted`.

El flag permanece desactivado por defecto. Antes de activarlo, configura estas
variables exclusivamente como secrets de Railway/environment; no las incluyas en
revisiones runtime, logs ni Git:

```env
# Generar una clave nueva: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
TELEGRAM_PAYLOAD_ENCRYPTION_KEY=<fernet-url-safe-base64-key>
TELEGRAM_PAYLOAD_KEY_VERSION=1
TELEGRAM_BOT_ID=<id-numerico-de-getMe>
TELEGRAM_ADMISSION_ENABLED=true
ALLOWED_TELEGRAM_USER_IDS=<id-telegram-permitido>
```

Con admission activado, faltan `ANCORA_DATABASE_URL`, `TELEGRAM_BOT_ID`,
`TELEGRAM_WEBHOOK_SECRET_TOKEN`, `TELEGRAM_PAYLOAD_ENCRYPTION_KEY` o una
allowlist no vacía hacen fallar el arranque de forma segura. La allowlist vacía
**no** significa «todos» en este modo.

### Control plane runtime (T6 de specs/013)

El control plane crea revisiones inmutables y activa una sola revisión para
futuros runs:

```env
RUNTIME_CONFIG_ADMIN_ENABLED=false
RUNTIME_CONFIG_BOOTSTRAP_DEFAULT_ROUTE=ancoramind-default
```

El token administrativo nunca se incluye en revisiones, logs ni Git:

```env
RUNTIME_CONFIG_ADMIN_TOKEN=<railway-secret-only>
```

Reglas:

- Schemas cerrados con `extra="forbid"` en todas las capas.
- Revisiones inmutables y activaciones append-only.
- `snapshot()` nunca hace I/O y es inmutable por run.
- Una revisión inválida conserva el último snapshot válido.
- Sin PostgreSQL al iniciar, usa bootstrap environment y las mutaciones
  devuelven `503`.
- Activación CAS con conflicto explícito `409`.
- Bearer obligatorio, CORS no habilitado y la API no se expone como tool.
- El operador se audita mediante `X-Ancora-Admin-Actor`.

Endpoints iniciales:

```text
GET  /admin/runtime-config/status
POST /admin/runtime-config/validate
POST /admin/runtime-config/revisions
POST /admin/runtime-config/revisions/{revision}/activate
POST /admin/runtime-config/rollback
```

`LISTEN/NOTIFY` queda explícitamente para el incremento posterior con una
réplica. El comando inicial es `scripts/runtime_config.py`; no incorpora
secretos en argumentos, archivos de configuración versionados ni respuestas.

Defaults iniciales de admission: 5 requests por usuario en 10 s, 10/minuto,
120/hora, 20 interacciones `accepted` globales y 5 por chat. La evaluación usa
PostgreSQL y un advisory lock transaccional; no depende de memoria del proceso.

### Processor y outbox Telegram (T5 de specs/013)

T5 añade un processor in-process, pero permanece apagado por defecto:

```env
TELEGRAM_PROCESSOR_ENABLED=false
TELEGRAM_PROCESSOR_POLL_INTERVAL_SECONDS=1.0
TELEGRAM_PROCESSOR_GLOBAL_CONCURRENCY=2
```

Solo puede arrancar si T4 admission también está activado y satisface sus
prerrequisitos fail-closed. Al iniciar, el processor marca como
`failed_ambiguous` cualquier interacción recuperada en `agent_started` o
`delivery_started`; nunca reejecuta el Agent ni reenvía una entrega incierta.
Recupera de forma segura `accepted` y `response_ready`.

Para cada run, usa lock por chat y usuario, un semáforo global de dos y una cola
ordenada por chat/fecha/update. Persiste una `logical_response` cifrada y las
filas de delivery por chunk antes de `sendMessage`; el streaming visible queda
desactivado y solo refresca `typing`. T7 ya usa `GovernedInteractionRunner`:
captura el snapshot runtime, crea `ExecutionContext` y `ExecutionBudget`, enlaza
un Agent nuevo por run y exige `LLMAccess` para cada model turn. El provider
directo era transitorio hasta T11: con `LITELLM_PROXY_ENABLED=true` la frontera
compone sólo `OpenAILike` hacia el LiteLLM privado (fail-closed, sin bypass).

El hard safety ceiling actual es `AGENT_TOOL_CALL_LIMIT=12`; Agent y Model usan
retries explícitos a cero. La extracción documental usa `DocumentExtractionPort`
(T9) detrás de `LLMAccess`; el webhook AgentOS legado permanece solo mientras
T4/T5 no estén activados.

T8 completa el presupuesto en los runs gobernados: aplica deadline total de
120 segundos, límites de model/Gateway calls, coste estimado y real opcional por
snapshot de pricing, y un hook async de Agno para tools. Este hook calcula un
HMAC de `tool + argumentos canónicos` con
`EXECUTION_BUDGET_FINGERPRINT_KEY` (o una subclave derivada de
`TELEGRAM_PAYLOAD_ENCRYPTION_KEY`), sin persistir ni exportar argumentos. Una
tool idéntica que ya tuvo éxito se bloquea; tras fallo solo hay un segundo intento
permitido. Agno recibe `StopAgentRun` y termina el loop sin otra inferencia.

El texto y los datos mínimos recuperables del update se serializan de forma
determinista, se cifran con Fernet y se guardan como `BYTEA`; el ledger conserva
un HMAC no reversible para correlación. Estados terminales normales eliminan el
payload inmediatamente. `failed_ambiguous` lo retiene hasta siete días y una
purga explícita elimina el ciphertext conservando metadata de auditoría.

### Alternativa local: PostgreSQL via Docker

```bash
# Arrancar solo PostgreSQL
docker compose up postgres -d
# Parar
docker compose down
```

### Aplicar migraciones

Alembic es la historia canónica del schema `ancora`. Lee
`ANCORA_DATABASE_URL` de las variables del proceso o `.env` y convierte la URL
`postgresql+asyncpg` a `postgresql+psycopg` para ejecutar las revisiones.

```bash
# PowerShell o Git Bash: aplicar hasta head
alembic upgrade head

# Ver revisión actual e historial
alembic current
alembic history

# Deshacer solo la última revisión
alembic downgrade -1
```

`migrations/init.sql` refleja el mismo schema que `head` y se conserva para
bootstrap fresh/local. Es idempotente, pero los upgrades sobre bases existentes
deben hacerse con Alembic.

```bash
# Bootstrap fresh alternativo — PowerShell:
Get-Content migrations/init.sql | docker compose exec -T postgres psql -U ancora -d ancoramind

# Bootstrap fresh alternativo — Git Bash:
docker compose exec -T postgres psql -U ancora -d ancoramind < migrations/init.sql
```

## Run

```bash
python -m src.main
```

Localmente requiere `.env` con `TELEGRAM_TOKEN` y, si se valida Telegram, un
webhook público autorizado. En Railway, el dominio estable sustituye a ngrok
(ver [deployment-railway.md](deployment-railway.md)). Sin
`ANCORA_DATABASE_URL` la app arranca igualmente pero sin domain tools
(degradación graceful).

Con `ANCORA_DATABASE_URL` + `TELEGRAM_TOKEN` la app arranca además el **worker
de recordatorios** (BL-5): dispara los `pending` vencidos y los notifica por
Telegram vía `sendMessage` (outbound, sin webhook — ver
[adr/ADR-003-reminder-worker.md](adr/ADR-003-reminder-worker.md)). Se desactiva
con `REMINDER_WORKER_ENABLED=false` y su cadencia se ajusta con
`REMINDER_POLL_INTERVAL_SECONDS`.

## Testing

```bash
# Unit tests (506 passing — repos y clientes externos mockeados)
pytest tests/unit/

# Integration tests (PostgreSQL real via docker compose — specs/009)
# La fixture arranca el contenedor sola; sin Docker se saltan (no fallan).
# La BD dedicada es ancoramind_test: la BD de dev (ancoramind) nunca se toca.
pytest tests/integration/

# Agentic eval catalogs (validación determinista; sin llamadas LLM)
python scripts/run_evals.py

# Todo (unit + integration)
pytest

# E2E tests (requiere stack completo)
pytest tests/e2e/
```

## Lint / Type check

```bash
ruff check src/
# Gate global en CI sobre `src/`; también debe ejecutarse antes de abrir una PR.
mypy src/
```

## Environment Variables

Ver [`.env.example`](../.env.example) para la lista completa (cargadas por
Pydantic Settings en `src/config.py`, `extra="ignore"`).

| Variable | Uso | Default |
|---|---|---|
| `LLM_PROVIDER` | `openai` \| `openrouter` \| `openai-like` | `openai` |
| `OPENAI_API_KEY` | API key (openai y openai-like) | — |
| `OPENROUTER_API_KEY` | API key (openrouter) | — |
| `LLM_MODEL` | Modelo | `gpt-6-luna` |
| `LLM_BASE_URL` | Endpoint custom (obligatorio en `openai-like`) | — |
| `AGENT_TOOL_CALL_LIMIT` | Límite duro de tools por ejecución; evita bucles de tool-calling | `8` |
| `TELEGRAM_TOKEN` | Token del bot (de @BotFather) | — |
| `TELEGRAM_WEBHOOK_SECRET_TOKEN` | Secret que Telegram envía al webhook; obligatorio al arrancar fuera de `development` | — |
| `APP_ENV` | Entorno; declarar `development` en local (relaja secret de webhook y guard REST) | `production` (default seguro — specs/023) |
| `AGENT_OS_SECURITY_KEY` | Bearer que protege la API REST de AgentOS; obligatorio fuera de `development` | — |
| `TELEGRAM_PAYLOAD_ENCRYPTION_KEY` | Clave Fernet para payload recuperable del ledger | — |
| `TELEGRAM_PAYLOAD_KEY_VERSION` | Versión de la clave Fernet | `1` |
| `TELEGRAM_ADMISSION_ENABLED` | Activa endpoint propio durable; requiere secretos/DB/allowlist | `false` |
| `TELEGRAM_BOT_ID` | ID numérico de `getMe`, identidad durable del bot | `0` |
| `TELEGRAM_ADMISSION_USER_BURST` | Máximo por usuario en ventana burst | `5` |
| `TELEGRAM_ADMISSION_BURST_WINDOW_SECONDS` | Ventana burst en segundos | `10` |
| `TELEGRAM_ADMISSION_USER_REQUESTS_PER_MINUTE` | Máximo por usuario/minuto | `10` |
| `TELEGRAM_ADMISSION_USER_REQUESTS_PER_HOUR` | Máximo por usuario/hora | `120` |
| `TELEGRAM_ADMISSION_PENDING_GLOBAL` | Capacidad máxima global en `accepted` | `20` |
| `TELEGRAM_ADMISSION_QUEUED_PER_CHAT` | Capacidad máxima `accepted` por chat | `5` |
| `TELEGRAM_PROCESSOR_ENABLED` | Inicia processor T5; requiere admission habilitado | `false` |
| `TELEGRAM_PROCESSOR_POLL_INTERVAL_SECONDS` | Cadencia de recuperación del processor | `1.0` |
| `TELEGRAM_PROCESSOR_GLOBAL_CONCURRENCY` | Máximo de chats procesados a la vez | `2` |
| `RUNTIME_CONFIG_ADMIN_ENABLED` | Expone la API admin T6; fail-closed sin DB/token | `false` |
| `RUNTIME_CONFIG_ADMIN_TOKEN` | Bearer HTTPS admin; solo Railway secrets | — |
| `RUNTIME_CONFIG_BOOTSTRAP_DEFAULT_ROUTE` | Ruta lógica bootstrap sin secrets | `ancoramind-default` |
| `NGROK_URL` | URL del túnel para el webhook | — |
| `PORT` | Puerto HTTP inyectado por Railway | `7777` local |
| `AGENT_OS_HOST` | Host HTTP opcional | `localhost` dev / `0.0.0.0` prod |
| `AGENT_OS_PORT` | Puerto HTTP local alternativo | `7777` |
| `AGNO_DATABASE_URL` | Runtime de Agno (si no: SQLite en `tmp/`) | — |
| `ANCORA_DATABASE_URL` | DB del dominio (schema `ancora`) — sin ella, sin domain tools | — |
| `DOCUMENT_STORAGE_BACKEND` | `local` \| `supabase` | `local` |
| `DOCUMENT_STORAGE_PATH` | Ruta del storage de documentos | `./data/documents` |
| `SUPABASE_URL` | URL base del proyecto (backend `supabase`) | — |
| `SUPABASE_SERVICE_ROLE_KEY` | Clave server-side de Storage | — |
| `SUPABASE_STORAGE_BUCKET` | Bucket privado de documentos | `ancora-documents` |
| `ALLOWED_TELEGRAM_USER_IDS` | Allowlist de user IDs (coma-separados); obligatoria con admission | vacío = todos solo en modo AgentOS legado; fail-closed en admission |
| `ANCORA_TEST_DATABASE_URL` | BD custom para integration tests (si no: docker compose) | — |
| `ANCORA_TEST_DATABASE` | Nombre de la BD dedicada de integration tests | `ancoramind_test` |
| `ANCORA_TEST_ADMIN_DSN` | DSN admin para crear la BD de integration tests | docker compose |
| `ANCORA_TEST_REQUIRE_DB` | `1` = fallar (en vez de saltar) sin PostgreSQL — usado en CI | — |
| `REMINDER_WORKER_ENABLED` | Arranca el worker de recordatorios (auto-gated con DB + token) | `true` |
| `REMINDER_POLL_INTERVAL_SECONDS` | Segundos entre ciclos de escaneo del worker | `60` |
| `LOG_LEVEL` | Nivel de logging | `INFO` |
| `OBSERVABILITY_JSON_LOGS` | Logs JSON metadata-only; el mensaje/args no se serializan | `true` |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | Endpoint gRPC del Collector privado; vacío = exporter desactivado fail-open | vacío |
| `OTEL_EXPORTER_OTLP_INSECURE` | Transporte sin TLS hacia private networking Railway | `true` |
| `OTEL_EXPORTER_OTLP_TIMEOUT_SECONDS` | Timeout acotado de exportación OTLP | `3` |
| `OTEL_EXPORT_INTERVAL_MILLIS` | Intervalo de exportación de métricas | `30000` |
| `HEALTH_PROBE_INTERVAL_SECONDS` | Cadencia de actualización de señales de health in-process | `30` |
| `HEALTH_GATEWAY_PROBE_TIMEOUT_SECONDS` | Timeout del probe privado LiteLLM; no afecta tráfico | `2` |
| `LITELLM_PROXY_ENABLED` | T11: enruta toda la inferencia por el Gateway privado (fail-closed) | `false` |
| `LITELLM_PROXY_BASE_URL` | URL privada del LiteLLM Proxy (requerida si el modo está activo) | — |
| `LITELLM_PROXY_VIRTUAL_KEY` | Key exclusiva AncoraMind creada con el script T11 | — |
| `LITELLM_PROXY_DEFAULT_ROUTE` | Alias base garantizado usado por el AgentOS legado; el runtime gobernado usa su revisión activa | `ancoramind-default-r1` |
| `LITELLM_VIRTUAL_KEY_RPM` | T12: RPM por virtual key en la creación de la key | `60` |
| `LITELLM_VIRTUAL_KEY_TPM` | T12: TPM por virtual key en la creación de la key | `250000` |
| `LITELLM_VIRTUAL_KEY_MAX_PARALLEL_REQUESTS` | T12: max parallel por virtual key | `4` |
| `LITELLM_VIRTUAL_KEY_MAX_BUDGET_USD` | T12: backstop USD opcional en el Gateway | — |
| `LITELLM_VIRTUAL_KEY_BUDGET_DURATION` | T12: ventana de rotación del backstop | `30d` |
| `LITELLM_VIRTUAL_KEY_ALIASES` | ADR-005: aliases runtime extra a autorizar en la key (preferir `grant`) | — |
| `APP_DEBUG` | Debug (echo de SQL) | `false` |

### Runbooks operativos specs/013 (T13)

Ver [`docs/runbooks-013.md`](runbooks-013.md): triage de AncoraMind sin
respuesta, Gateway down (fail closed), circuit breaker automático
(`3` fallos / `60 s` de cooldown), cambio de modelo en caliente por publicación
de alias en dos fases, budget exhausted (`failed_controlled` sin replay),
`failed_ambiguous` (sin replay/reenvío), Collector down (fail open),
rollback CAS de config y checklist pendiente del rollout (E2E Railway,
benchmark con clave real, Grafana, rotación real). El endpoint adicional
`GET /health/readiness` entrega sólo metadata in-memory (sin I/O durante el
request); sus probes se ejecutan en background y no sustituyen `/health`.

### Runtime dinámico y LLMAccess (BL-23/specs/013)

T6 implementa `RuntimeConfigManager` cacheado en memoria; T7 captura ese
snapshot por run y crea un Agent nuevo gobernado. El hard safety ceiling actual
es `AGENT_TOOL_CALL_LIMIT=12`; Agent y Model usan retries explícitos a cero.

Todavía quedan límites deliberados:

- cambiar el provider/model físico de environment sigue requiriendo restart;
- con el Gateway desactivado, OpenRouter/provider directo solo está permitido
  dentro de `LLMAccess`; con `LITELLM_PROXY_ENABLED=true` (T11) no existe ruta
  directa y un Gateway caído falla cerrado sin fallback;
- la extracción documental ya pasa por `DocumentExtractionPort`/`LLMAccess`
  (T9); el path AgentOS legado usa un contexto bootstrap standalone;
- T10 fuerza `AGNO_TELEMETRY=false` y `telemetry=False`, emite trazas/métricas
  OTel y logs JSON metadata-only mediante allowlist. El exporter al Collector
  privado es opcional/fail-open; el rollout real Railway/Grafana sigue pendiente;
- T11 deja el pilot del Gateway validado localmente; el rollout Railway
  (PostgreSQL dedicado + servicio privado), el benchmark con clave real y la
  revisión de superficie productiva requieren aprobación explícita.
- T12 añade `CostGovernanceConfig` (límite externo + umbrales 60/80/90 + budgets
  día/mes/ruta) con invariante en rutas de pago. El runner evalúa el spend
  agregado de `llm_usage_events` al inicio de cada run (fail-closed si hay
  gobernanza sin reader); hard stop ⇒ `failed_controlled` sin replay. El
  Gateway declara circuit breaker (`allowed_fails/cooldown_time`) y RPM/TPM por
  alias + límites por virtual key. Retries/fallbacks siguen a 0 por decisión.

### Panel FinOps y calidad (specs/043)

`/admin/dashboard` incluye el panel «FinOps y calidad», de sólo lectura. Lo sirven
`GET /admin/dashboard/api/finops` y `/api/quality` (`days` 1–90, por defecto 30, días
UTC incluyendo hoy; fuera de rango ⇒ 422). Usa el mismo token admin que el resto del
dashboard y sólo consulta `llm_usage_events`, `telegram_interactions` y
`action_proposals`. No devuelve contenido, `payload` ni IDs de Telegram: el usuario
sale como `u-` + 8 hex de un HMAC con `TELEGRAM_PAIRING_CODE_PEPPER`. Es una
protección frente a capturas, no anonimización. Medición de consultas:
`specs/043-admin-finops-quality-panel/explain.md`.

**Qué NO incluye el coste del panel** (el panel lo rotula con «No incluido en el coste»):

- **Dream** (`dream_runs`): audita su inferencia en su propia tabla, fuera del ledger.
  Tampoco entra en el hard stop (`evaluate_cost_governance`).
- **Voz sin evento**: filas de `voice_preparations` con `call_id` y sin fila en
  `llm_usage_events`. El panel las ignora, pero `LlmUsageRepository.summarize_spend`
  sí las suma.
- **Interacciones `rejected`/`ignored`**: nunca ejecutaron el Agent, así que no
  aportan coste en el panel. Sí cuentan en «Interacciones por estado» (calidad).
- **Coste estimado**: sin `actual_cost` se usa `estimated_cost`; el desglose por
  `cost_source` lo separa. No es una factura.

**Cuándo el panel y el hard stop pueden diferir.** El coste usa
`COALESCE(actual_cost, estimated_cost, 0)`, igual que `summarize_spend`, y el test de
integración comprueba que coinciden para el mismo periodo. Esa paridad sólo vale sin
voz sin evento. Las barras de presupuesto (mes/hoy) salen de `summarize_spend`, por lo
que **sí** incluyen esa voz, mientras que los KPIs del panel no. Si «Coste total» de
un mes natural es menor que la barra «Mes», la diferencia es voz sin evento. El panel
tampoco reproduce el reparto por ruta del presupuesto.

El presupuesto es `null` (se muestra «Sin presupuesto configurado») si la revisión
activa no tiene `cost_governance`.


## Project Conventions

- **No Agno inheritance in domain code** — domain services are plain Python;
  extracción documental usa el port `DocumentExtractionPort`.
- **Tools are thin adapters** — they call domain services, never contain business logic
- **Parameterized queries only** — no string interpolation in SQL
- **User context from runtime, never from LLM**
- **Prompts in Git, not in code strings**
- **Añadir una tool nueva** — guía paso a paso: [adding-tools.md](adding-tools.md)

## Related Docs

- [AGENTS.md](../AGENTS.md) — contexto para agentes de IA (manda junto con architecture.md)
- [quick-start.md](quick-start.md) — arranque día a día
- [deployment-e2e.md](deployment-e2e.md) — primera configuración
- [architecture.md](architecture.md) — arquitectura
- [governance.md](governance.md) — gobernanza de acciones WRITE
- [../BACKLOG.md](../BACKLOG.md) — pendientes priorizados
