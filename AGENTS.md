# AGENTS.md — Contexto para Agentes de Programación

> Guía para asistentes de IA que trabajan en este repositorio.
> Última actualización: 2026-10-03

---

## 1. Qué es este proyecto

**AncoraMind** — asistente personal agentic (POC/MVP) que convierte información
cotidiana desordenada en memoria operativa: notas, documentos, datos de vehículos,
recordatorios y eventos, con trazabilidad completa.

- **Runtime agentic:** Agno + AgentOS (infraestructura reemplazable)
- **Canal:** Telegram (solo private chats)
- **Base de datos canónica:** PostgreSQL (schema `ancora`, separado de `agno_runtime`)
- **Lenguaje:** Python 3.12+
- **Estado actual:** Milestones M1–M5 completos (ver §8) + listas TODO. 643 unit
  tests + 94 integration tests; los integration requieren PostgreSQL/Docker
  (se omiten sin esa infraestructura). Ruff y `mypy src/` limpios; ambos son
  gates globales en CI.

---

## 2. Principios arquitectónicos NO negociables

Estas reglas vienen del brief de ingeniería. **No violarlas aunque parezca más simple:**

1. **Agno es infraestructura reemplazable; AncoraMind Core es el producto.**
   La lógica de negocio (`src/domain/`) NUNCA hereda de clases de Agno. Debe poder
   invocarse desde REST API, CLI, MCP, u otro runtime sin duplicación.

2. **Añadir capacidad ≈ añadir Tool.** Un solo agente principal. Sin routers,
   sin subagentes, sin workflows nuevos salvo necesidad demostrable.

3. **Frontera probabilístico/determinista.** El LLM decide *qué capability
   solicitar*; el Core decide *qué permisos tiene*. La identidad del usuario
   (UserContext) NUNCA procede del LLM — se resuelve del `RunContext` de Agno.

4. **Toda operación WRITE/EXTERNAL_ACTION/DESTRUCTIVE requiere gobernanza.** Patrón ActionProposal:
   `propose_*` crea propuesta `pending_confirmation` → usuario confirma ("Sí")
   → `execute_*` valida, ejecuta y audita. Ejemplos:
   `propose_vehicle_maintenance` / `execute_vehicle_maintenance`.
   **Excepción aprobada (specs/023 T4.7, 2026-10-02):** `analyze_document`/
   `DocumentService.ingest` siguen siendo automáticos — enviar un adjunto ya
   es la señal de intención de guardarlo; pedir confirmación añadiría
   fricción innecesaria para el caso común. A cambio existe
   `propose_document_delete`/`execute_document_delete` (DESTRUCTIVE,
   gobernado) para el caso "no quiero esto guardado".

5. **SQL siempre parametrizado.** Solo `sqlalchemy.text()` con bind params.
   Nunca interpolación de strings. Toda query scoped por `user_id`.

6. **Prompts en Git, no en código.** Los prompts viven en `prompts/*.md`
   (identity, soul, tool_contract, channels/, skills/). No meter instrucciones
   críticas como strings anónimos en Python.

7. **Separación de DBs.** Agno persiste su runtime donde quiera
   (`agno_database_url`); el dominio usa `ancora_database_url` → schema `ancora`.
   AncoraMind Core jamás depende de las tablas internas de Agno.

8. **Datos no confiables = DATA, no INSTRUCTIONS.** Contenido de documentos,
   filenames, extracciones IA no pueden cambiar permisos ni instrucciones.

9. **El acceso LLM es una capability gobernada (target BL-23/specs/013).** Toda
   inferencia deberá pasar por `LLMAccess`, con ruta lógica versionada,
   `RuntimeConfigSnapshot`, `ExecutionContext`, budget, coste y correlación. No
   crear providers físicos directamente en domain/services/tools.

10. **Idempotencia Telegram ≠ rate limiting.** El target es
    `same bot_id + update_id => at most one Agent execution`. Duplicados reciben
    `2xx` sin IA; después de `agent_started` no hay replay automático.

11. **Observabilidad sin contenido personal (target BL-23/specs/013).** Usar
    OpenTelemetry + Collector privado + Grafana Cloud con allowlist de metadata.
    No prompts, mensajes, respuestas, documentos ni argumentos/resultados
    completos. La auditoría durable permanece en PostgreSQL.

---

## 3. Estructura del repositorio

```
src/
├── main.py              ← Entry point: AgentOS + Telegram + registro de tools
├── config.py            ← Pydantic Settings (.env). extra="ignore"
├── agent/               ← Capa Agno (infraestructura)
│   ├── ancora_agent.py  ← factory física legado + SafeOpenRouter; T7 la compone con GovernedModel
│   ├── llm_access.py / governed_model.py / governed_agent_factory.py /
│   │   governed_interaction_runner.py ← T7: LLMAccess + Agent por run
│   ├── instructions.py  ← assemble_instructions(): carga prompts/*.md → list[str]
│   ├── lifecycle.py     ← lifespan FastAPI: worker recordatorios auto-gated (BL-22)
│   ├── server.py        ← host/PORT/reload para local y Railway
│   ├── telegram_webhook.py ← helper de registro; telegram_admission.py ← endpoint T4
│   ├── context.py       ← legado; UserContext canónico está en security/
│   └── tools/           ← Thin adapters (UNA función por capability)
│       ├── system.py      notes.py      documents.py
│       ├── vehicles.py    maintenance.py (propose/execute)
│       ├── reminders.py   calendar.py    todos.py (propose/execute estricto)
├── domain/              ← Lógica de negocio (el producto — sin imports de Agno*)
│   ├── notes/ documents/ vehicles/ reminders/ calendar/ todos/ actions/ interactions/ llm_access/
│   └── (cada uno: models.py + service.py; calendar tiene provider.py Protocol;
│       reminders tiene worker.py sin dependencia de FastAPI; documents expone
│       DocumentExtractionPort — T9 abstrajo la extracción del runtime;
│       interactions/commands.py resuelve los comandos de bot `/new` y `/help`
│       antes de cualquier ejecución del Agent — BL-28)
├── repositories/        ← Acceso PostgreSQL (sqlalchemy async, text() parametrizado)
│   ├── database.py      ← init_database(), get_session() — llamar init al arrancar
│   └── notes, documents, vehicles, maintenance, reminders, calendar, todos, actions,
│       interactions, llm_usage (ledger/usage durable — specs/013)
├── storage/             ← base.py (DocumentStorage Protocol), local.py, supabase_storage.py,
│                           factory.py (DOCUMENT_STORAGE_BACKEND: local|supabase — ADR-002)
├── security/            ← user_context.py (UserContext.from_run_context)
├── notifications/       ← telegram.py (TelegramNotifier — entrega outbound BL-5/ADR-003)
│                           + markup.py (Markdown del modelo → HTML de Telegram, BL-29)
└── governance/          ← (metadata, riesgo — en desarrollo)

AGENTS.md                 ← Esta guía (jerarquía: manda junto con docs/architecture.md)
BACKLOG.md                ← Lista viva y priorizada de pendientes (fuente única de verdad)
prompts/                 ← Assets de IA versionados (identity, soul, tool_contract,
│                           channels/telegram.md, skills/)
migrations/              ← Alembic canónico (baseline + revisiones); init.sql
│                           refleja head para bootstrap fresh — BL-12/specs/013
scripts/                 ← run-e2e.sh + run-e2e.ps1 + telegram_webhook.py + runtime_config.py (admin T6)
                            + litellm_create_virtual_key.py (T11 Gateway)
                            + litellm_gateway_alias.py (ADR-005: publicar/otorgar/
                              retirar aliases versionados en caliente)
                            + run_evals.py (BL-8: validación determinista de catálogos)
specs/                   ← SDD: 001-runtime, 002-notes, 003-documents, 004-vehicle,
                            005-calendar, 006-vehicle-creation, 007-supabase,
                            008-railway-deployment, 009-integration-tests,
                            010-reminder-worker, 011-todo-lists, 012-fastapi-lifespan,
                            013-llm-access-governance (T2–T14 implementados localmente),
                            014-agentic-evals (base determinista) +
                            018-agentic-evals-execution-harness (harness aislado),
                            015-powershell-e2e (implementada),
                            016-health-dashboard (en curso — BL-33),
                            017-telegram-governed-pairing (implementada),
                            019-mypy-hardening + 020-mypy-ci-gate (gate global en
                            CI), 021-document-conversion-toolkit (Fase 1 lista para
                            implementar — BL-38), 022-llm-input-trust (primer
                            incremento local — BL-39),
                            023-audit-remediation (Fases 1–5 implementadas
                            localmente; Fase 6 en curso — BL-40)
tests/unit/              ← 643 tests
tests/integration/        ← 94 tests (PostgreSQL dockerizado — specs/009; skip sin Docker)
evals/                   ← Catálogos sintéticos versionados (BL-8/specs/014 + 018)
docs/                    ← architecture, governance, development, quick-start,
                           deployment-e2e, deployment-railway, runbooks-013
                           (operación specs/013), adding-tools (guía para nuevas
                           tools),
                           adr/ADR-001-agno-runtime.md,
                           adr/ADR-002-supabase-infrastructure.md,
                           adr/ADR-003-reminder-worker.md,
                           adr/ADR-004-telegram-admission-at-most-once.md,
                           adr/ADR-005-governed-llm-access-runtime-config.md,
                           adr/ADR-006-opentelemetry-observability.md
gateway/                 ← LiteLLM Proxy pilot (T11/T12): config sin secretos, circuit breaker + RPM/TPM
                           con imagen fijada por digest y compose local de validación;
                           store_model_in_db permite publicar aliases r2+ en caliente
                           (ADR-005 enmendado — nunca editar un alias en uso)
observability/           ← Manifiesto del OTel Collector privado (T10)
```

***\*Sin excepciones:*** `domain/` no importa Agno. La extracción documental
usa `DocumentExtractionPort` (T9); su adaptador Agno vive en `src/agent/`
y pasa por `LLMAccess`.

---

## 4. Convenciones de código

- **Tools = funciones Python planas async.** Agno las convierte en tools por el
  docstring y type hints. El docstring es la descripción que ve el LLM —
  escribirlo con cuidado (cuándo usar la tool, ejemplos de frases del usuario).
- **`run_context: RunContext`** como primer parámetro de toda tool → inyección
  automática de Agno (no va al schema del LLM).
- **Devolver strings formateados en español** desde las tools (el usuario habla
  español). Estructura: título en negrita, datos alineados, emojis moderados.
- **Resultados de repos:** modelos Pydantic con `model_config = {"from_attributes": True}`.
- **Pydantic v2:** para campos opcionales usar `X | None = None` (con
  `from __future__ import annotations` si hay shadowing de nombres).
  Evitar `Optional[X] = Field(default=None)` (bug de generación de schema).
- **Servicios de domain** reciben repositorios por constructor (inyección manual).
- **Config:** todo por env vars vía `Settings` en `config.py`. Nunca hardcodear
  credenciales ni URLs.
- **Comandos de bot:** se resuelven en `domain/interactions/commands.py` antes de
  cualquier ejecución del Agent (BL-28). Nunca llegan al LLM ni arrastran el
  historial al proveedor; sus replies son constantes en código (así el texto del
  usuario no puede convertirse en instrucción por esta vía). Añadir un comando =
  entrada en el mapa + reply constante + tests.
- **Formato de entrega:** las respuestas del modelo se renderizan a HTML de
  Telegram en `notifications/markup.py` (BL-29): todo el texto literal se escapa y
  las etiquetas salen sólo de una whitelist del módulo. Nunca declarar
  `parse_mode` en otro sitio ni interpolar contenido sin escapar; si Telegram
  rechaza el markup, la entrega reintenta en texto plano en vez de perderse.

### Proveedores LLM (factory en `ancora_agent.py`)

| `LLM_PROVIDER` | Clase Agno | API key env var | `LLM_BASE_URL` |
|---|---|---|---|
| `openai` | `OpenAIChat` | `OPENAI_API_KEY` | opcional |
| `openrouter` | `OpenRouter` | `OPENROUTER_API_KEY` | automático |
| `openai-like` | `OpenAILike` | `OPENAI_API_KEY` | **requerido** |

Modo Gateway (T11): con `LITELLM_PROXY_ENABLED=true` la tabla anterior se ignora
— `LLMAccess` y el AgentOS legado componen únicamente `OpenAILike` hacia el
LiteLLM privado (`LITELLM_PROXY_BASE_URL` + `LITELLM_PROXY_VIRTUAL_KEY`,
fail-closed si faltan), usando el alias versionado del snapshot como `model`.
La virtual key se crea con `scripts/litellm_create_virtual_key.py`; los secretos
del provider viven sólo en el Gateway (`gateway/litellm-config.yaml` no contiene
secretos). Un Gateway caído ⇒ error de inferencia, nunca fallback directo.

Modelo default para acceso directo/desarrollo: `gpt-6-luna`. Con el Gateway,
GPT-6 Luna usa el alias gobernado `ancoramind-default-r3` tras publicarlo y
activar su revisión runtime. Los modelos free de OpenRouter caducan — si hay
error 404, cambiar `LLM_MODEL` en `.env`.

**Cambiar el modelo físico (ADR-005, enmendado 2026-09-18):** con el Gateway
activo `LLM_PROVIDER`/`LLM_MODEL` se ignoran. El cambio se hace publicando un
alias versionado **nuevo** (`r2`, `r3`, …) con
`scripts/litellm_gateway_alias.py` y activando una revisión de runtime config
que apunte a él: sin redeploy y sin mutar el alias en uso. Prohibido editar un
alias existente (rompe la trazabilidad de `effective_gateway_route`). Ver
`docs/runbooks-013.md` §2.2.

---

## 5. Comandos

> Los comandos que usan `<` (redirección bash) **no funcionan en PowerShell**.
> Se indica la alternativa para cada shell cuando sea necesario.

```bash
# Activar venv (PowerShell)
.venv/Scripts/Activate.ps1

# Activar venv (Git Bash)
source .venv/Scripts/activate

# Tests unitarios
python -m pytest tests/unit/ -v

# Integration tests (71 — PostgreSQL dockerizado; se saltan sin Docker)
python -m pytest tests/integration/ -v

# Lanzar la app localmente (requiere .env + PostgreSQL/Supabase; webhook solo
# si se valida Telegram mediante una exposición HTTPS autorizada)
python -m src.main

# PostgreSQL (Docker)
docker compose up postgres -d
docker compose down

# Aplicar migraciones canónicas (PowerShell o Git Bash)
alembic upgrade head

# Bootstrap fresh alternativo (PowerShell)
Get-Content migrations/init.sql | docker compose exec -T postgres psql -U ancora -d ancoramind

# Bootstrap fresh alternativo (Git Bash)
docker compose exec -T postgres psql -U ancora -d ancoramind < migrations/init.sql

# Instalar dependencias
pip install -e ".[dev]"

# Lint (gate global — también en CI)
ruff check src/ tests/ scripts/ migrations/

# Type checking (gate global en CI desde specs/020)
mypy src/
```

---

## 6. Modelo de datos (schema `ancora`)

| Tabla | Propósito | Notas |
|---|---|---|
| `notes` | Memoria canónica de notas | user_id, content |
| `documents` | Registro de documentos | storage_key → local/Supabase Storage, provenance |
| `ai_extractions` | Resultados IA (JSONB) | provider, model, prompt_version, confidence |
| `vehicles` | Vehículos del usuario | make, model, nickname, registration |
| `vehicle_maintenance` | Historial de mantenimiento | FK vehicle, FK source_document |
| `reminders` | Recordatorios | trigger_at, status, provenance |
| `calendar_events` | Eventos canónicos | provider_event_id (NoopCalendarProvider) |
| `action_proposals` | Gobernanza WRITE | pending_confirmation → confirmed → executed |
| `todo_lists` | Listas TODO canónicas | user_id, name, timestamps |
| `todo_items` | Tareas de una lista TODO | FK list ON DELETE CASCADE, status, prioridad, due_date, position |

**Tres tipos de memoria:** runtime/conversacional (Agno DB) ≠ soft personal
(auxiliar) ≠ **canónica (schema `ancora` — fuente de verdad, siempre gana)**.

---

## 7. Gobernanza (resumen)

- Clasificación de riesgo: `READ` < `WRITE` < `EXTERNAL_ACTION` < `DESTRUCTIVE`
- READ → directa. WRITE/EXTERNAL_ACTION/DESTRUCTIVE → ActionProposal + confirmación humana.
  No hay excepciones por reversibilidad: las mutaciones TODO de listas **e ítems**
  usan `propose_*` → confirmación → `execute_*`.
- Auditoría: action_proposals registra confirm/execute timestamps + provenance
  (`source_document_id`)
- Comandos de bot (`/new`, `/help`): control determinista, sin propuesta — no
  escriben datos canónicos ni llaman a proveedores. `/new` sólo abre una nueva
  generación de conversación, registrada en el ledger de interacciones.
- Detalle completo: `docs/governance.md`

---

## 8. Estado y roadmap

| Milestone | Estado |
|---|---|
| M1 Agent Runtime (Telegram+Agno+session) | ✅ |
| M2 Canonical Memory (notes) | ✅ |
| M3 Document Memory (storage+extraction) | ✅ |
| M4 Vehicle vertical slice | ✅ |
| M5 Calendar & Reminders | ✅ (worker outbound con FastAPI lifespan) |
| BL-21 Listas TODO multi-lista | ✅ (toda mutación gobernada) |
| BL-8 Evals agentic | 🔶 19 casos sintéticos, runner estático y harness aislado; pendiente adaptador contra Agent/LLM gobernado (specs/014 + 018) |
| BL-18 Railway como sustituto de ngrok | 🔶 Servicio/dominio/webhook/healthcheck reales validados; pendiente Wait for CI + E2E M3–M5 (specs/008) |
| BL-25 Script E2E nativo PowerShell | ✅ `run-e2e.ps1` local/remoto con `.env` seguro (specs/015) |
| BL-23 Governed LLM Access + Telegram admission + OTel | 🔶 T2–T14 implementados; T14 fase 6 (cambio de modelo en caliente) validado en Railway (2026-09-19); pendientes: rollout Collector/Grafana, E2E completo y rotaciones (specs/013) |
| BL-33 Health signals + dashboard de salud | 🔶 T1–T6 implementados localmente (readiness metadata-only, probes acotados, dashboard y alertas versionadas); pendiente validación real Collector/Grafana/Railway (T7, specs/016) |
| MVP usable | 🔶 E2E parcialmente validado (M1-M2 probado en Telegram; M3-M5 pendiente) |

**Backlog:** la lista viva y priorizada de pendientes está en `BACKLOG.md`
(fuente única de verdad). La prioridad P0 es BL-23/specs/013; después siguen
E2E de M3–M5, despliegue Railway (specs/008), OCR real, proveedor de calendario
real y evals agentic.

**Fuera de alcance (explícitamente "not yet"):** GraphRAG, vector search,
multi-agent, WhatsApp, web frontend, microservices, event sourcing.

---

## 9. Decisiones arquitectónicas clave

- **ADR-001:** Agno + AgentOS como runtime. Alternativas (Pydantic AI, LangGraph,
  custom loop) evaluadas y descartadas para el POC. No re-abrir el debate sin
  autorización. Si Agno bloquea un requisito: documentar → demostrar → proponer
  alternativas → pedir decisión.
- **ADR-004:** admission Telegram propiedad de AncoraMind, idempotencia durable
  y semántica at-most-once del Agent.
- **ADR-005:** `LLMAccess`, configuración runtime versionada y LiteLLM Proxy
  privado/fail-closed con OpenRouter upstream.
- **ADR-006:** OpenTelemetry + Collector privado + Grafana Cloud; telemetría de
  producto Agno desactivada al activar el pipeline propio.
- **n8n:** no consultar, migrar ni traducir (implementación anterior). Solo
  requisitos funcionales y aprendizajes de seguridad.

---

## 10. Al hacer cambios

1. **Añadir capability nueva** = models + repository + service + tool +
   registro en `_init_domain_tools()` (main.py) + tests + skill prompt si aplica.
   Seguir el patrón de `notes` (la más sencilla y completa).
   **Guía detallada paso a paso: `docs/adding-tools.md`.**
2. **Operación WRITE/EXTERNAL_ACTION/DESTRUCTIVE** → siempre par `propose_*` /
   `execute_*` con ActionProposal. La propuesta no escribe datos canónicos; el
   executor confirma, revalida autorización/propiedad, ejecuta y audita.
3. **Tests:** los unit tests mockean repositorios (`AsyncMock(spec=Repo)`).
   Ejecutar `pytest tests/unit/` antes de dar nada por terminado.
4. **Cambiar prompts/models/tool descriptions** = cambio evaluable (gobernanza).
   Anotarlo en el commit.
5. **Migraciones:** Alembic es la historia canónica desde BL-12/specs/013.
   Añadir una revisión en `migrations/versions/` y mantener `migrations/init.sql`
   equivalente a `head` para bootstrap fresh. Probar fresh install, upgrade sobre
   datos y downgrade de la última revisión.
6. **Jerarquía de docs:** si algo contradice entre documentos, este fichero y
   `docs/architecture.md` mandan sobre el resto.
7. **Cambios de inferencia/config/telemetry:** seguir specs/013. No añadir retries,
   fallbacks, providers directos, captura de contenido o bypass del Gateway sin
   actualizar la policy y sus acceptance tests.
8. **Cambiar el modelo físico:** publicar un alias versionado nuevo con
   `scripts/litellm_gateway_alias.py` (`publish` → `grant` → `verify`) y activar
   una revisión runtime que apunte a él. Nunca editar ni retirar un alias en uso;
   nunca escribir settings del Gateway por API/UI (ADR-005 enmendado).

---

## 11. Estilo de comunicación

Preferencia del propietario sobre cómo se comunican los agentes en este repositorio:

- **Respuestas moderadas de longitud.** Explicar qué se hizo y el resultado de la
  verificación, pero sin narrar cada paso ni pegar código ya editado en la respuesta.
- Ni exhaustivas ni telegráficas: un resumen claro de cambios + cualquier
  decisión/limitación relevante. El propietario pedirá más detalle si lo necesita.
- Estructura preferida: qué cambió → cómo se validó → puntos que requieren
  atención. Sin relleno ni secciones ceremoniales.
