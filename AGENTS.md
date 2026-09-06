# AGENTS.md — Contexto para Agentes de Programación

> Guía para asistentes de IA que trabajan en este repositorio.
> Última actualización: 2026-08-27

---

## 1. Qué es este proyecto

**AncoraMind** — asistente personal agentic (POC/MVP) que convierte información
cotidiana desordenada en memoria operativa: notas, documentos, datos de vehículos,
recordatorios y eventos, con trazabilidad completa.

- **Runtime agentic:** Agno + AgentOS (infraestructura reemplazable)
- **Canal:** Telegram (solo private chats)
- **Base de datos canónica:** PostgreSQL (schema `ancora`, separado de `agno_runtime`)
- **Lenguaje:** Python 3.12+
- **Estado actual:** Milestones M1–M5 completos (ver §8). 82 tests passing.

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

4. **WRITE/EXTERNAL_ACTION requiere gobernanza.** Patrón ActionProposal:
   `propose_*` crea propuesta `pending_confirmation` → usuario confirma ("Sí")
   → `execute_*` valida, ejecuta y audita. Ejemplos:
   `propose_vehicle_maintenance` / `execute_vehicle_maintenance`.

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

---

## 3. Estructura del repositorio

```
src/
├── main.py              ← Entry point: AgentOS + Telegram + registro de tools
├── config.py            ← Pydantic Settings (.env). extra="ignore"
├── agent/               ← Capa Agno (infraestructura)
│   ├── ancora_agent.py  ← create_model() (3 providers), create_db(), create_ancora_agent()
│   ├── instructions.py  ← assemble_instructions(): carga prompts/*.md → list[str]
│   ├── context.py       ← UserContext dataclass
│   └── tools/           ← Thin adapters (UNA función por capability)
│       ├── system.py      notes.py      documents.py
│       ├── vehicles.py    maintenance.py (propose/execute)
│       ├── reminders.py   calendar.py
├── domain/              ← Lógica de negocio (el producto — sin imports de Agno*)
│   ├── notes/ documents/ vehicles/ reminders/ calendar/ actions/
│   └── (cada uno: models.py + service.py; calendar tiene provider.py Protocol)
├── repositories/        ← Acceso PostgreSQL (sqlalchemy async, text() parametrizado)
│   ├── database.py      ← init_database(), get_session() — llamar init al arrancar
│   └── notes, documents, vehicles, maintenance, reminders, calendar, actions
├── storage/             ← base.py (DocumentStorage Protocol), local.py (filesystem)
├── security/            ← user_context.py (UserContext.from_run_context)
└── governance/          ← (metadata, riesgo — en desarrollo)

AGENTS.md                 ← Esta guía (jerarquía: manda junto con docs/architecture.md)
BACKLOG.md                ← Lista viva y priorizada de pendientes (fuente única de verdad)
prompts/                 ← Assets de IA versionados (identity, soul, tool_contract,
│                           channels/telegram.md, skills/)
migrations/init.sql      ← Schema completo del dominio (9 tablas + indexes)
scripts/run-e2e.sh       ← Despliegue automatizado (bash)
specs/                   ← SDD: 001-runtime, 002-notes, 003-documents, 004-vehicle,
                            005-calendar (spec.md + tasks.md + verification.md)
tests/unit/              ← 82 tests
evals/                   ← Carpetas por categoría (vacías — pendiente)
docs/                    ← architecture, governance, development, quick-start,
                           deployment-e2e, adding-tools (guía para nuevas tools),
                           adr/ADR-001-agno-runtime.md
```

***\*Excepción aceptada:*** `domain/documents/service.py` usa `agno.agent.Agent`
para la extracción IA con `output_schema` — única incursión del runtime en domain,
pendiente de abstraer si se cambia de framework.

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

### Proveedores LLM (factory en `ancora_agent.py`)

| `LLM_PROVIDER` | Clase Agno | API key env var | `LLM_BASE_URL` |
|---|---|---|---|
| `openai` | `OpenAIChat` | `OPENAI_API_KEY` | opcional |
| `openrouter` | `OpenRouter` | `OPENROUTER_API_KEY` | automático |
| `openai-like` | `OpenAILike` | `OPENAI_API_KEY` | **requerido** |

Modelo default: `gpt-5.4-mini`. Los modelos free de OpenRouter caducan —
si hay error 404, cambiar `LLM_MODEL` en `.env`.

---

## 5. Comandos

> Los comandos que usan `<` (redirección bash) **no funcionan en PowerShell**.
> Se indica la alternativa para cada shell cuando sea necesario.

```bash
# Activar venv (PowerShell)
.venv/Scripts/Activate.ps1

# Activar venv (Git Bash)
source .venv/Scripts/activate

# Tests (82 passing)
python -m pytest tests/unit/ -v

# Lanzar la app (requiere .env + PostgreSQL + ngrok + webhook)
python -m src.main

# PostgreSQL (Docker)
docker compose up postgres -d
docker compose down

# Aplicar migraciones (PowerShell)
Get-Content migrations/init.sql | docker compose exec -T postgres psql -U ancora -d ancoramind

# Aplicar migraciones (Git Bash)
docker compose exec -T postgres psql -U ancora -d ancoramind < migrations/init.sql

# Instalar dependencias
pip install -e ".[dev]"

# Lint / type check
ruff check src/
mypy src/
```

---

## 6. Modelo de datos (schema `ancora`)

| Tabla | Propósito | Notas |
|---|---|---|
| `notes` | Memoria canónica de notas | user_id, content |
| `documents` | Registro de documentos | storage_key → filesystem, provenance |
| `ai_extractions` | Resultados IA (JSONB) | provider, model, prompt_version, confidence |
| `vehicles` | Vehículos del usuario | make, model, nickname, registration |
| `vehicle_maintenance` | Historial de mantenimiento | FK vehicle, FK source_document |
| `reminders` | Recordatorios | trigger_at, status, provenance |
| `calendar_events` | Eventos canónicos | provider_event_id (NoopCalendarProvider) |
| `action_proposals` | Gobernanza WRITE | pending_confirmation → confirmed → executed |

**Tres tipos de memoria:** runtime/conversacional (Agno DB) ≠ soft personal
(auxiliar) ≠ **canónica (schema `ancora` — fuente de verdad, siempre gana)**.

---

## 7. Gobernanza (resumen)

- Clasificación de riesgo: `READ` < `WRITE` < `EXTERNAL_ACTION` < `DESTRUCTIVE`
- READ → directa. WRITE/EXTERNAL_ACTION → ActionProposal + confirmación humana
- Auditoría: action_proposals registra confirm/execute timestamps + provenance
  (`source_document_id`)
- Detalle completo: `docs/governance.md`

---

## 8. Estado y roadmap

| Milestone | Estado |
|---|---|
| M1 Agent Runtime (Telegram+Agno+session) | ✅ |
| M2 Canonical Memory (notes) | ✅ |
| M3 Document Memory (storage+extraction) | ✅ |
| M4 Vehicle vertical slice | ✅ |
| M5 Calendar & Reminders | ✅ |
| MVP usable | 🔶 E2E parcialmente validado (M1-M2 probado en Telegram; M3-M5 pendiente) |

**Backlog:** la lista viva y priorizada de pendientes está en `BACKLOG.md`
(fuente única de verdad). Los items priorizados son: E2E de M3–M5,
integration tests con PostgreSQL real, migración a Supabase, background worker
de recordatorios, OCR real, proveedor de calendario real, evals agentic y
unificar la factory de modelo en tools de documentos.

**Fuera de alcance (explícitamente "not yet"):** GraphRAG, vector search,
multi-agent, WhatsApp, web frontend, microservices, event sourcing.

---

## 9. Decisiones arquitectónicas clave

- **ADR-001:** Agno + AgentOS como runtime. Alternativas (Pydantic AI, LangGraph,
  custom loop) evaluadas y descartadas para el POC. No re-abrir el debate sin
  autorización. Si Agno bloquea un requisito: documentar → demostrar → proponer
  alternativas → pedir decisión.
- **n8n:** no consultar, migrar ni traducir (implementación anterior). Solo
  requisitos funcionales y aprendizajes de seguridad.

---

## 10. Al hacer cambios

1. **Añadir capability nueva** = models + repository + service + tool +
   registro en `_init_domain_tools()` (main.py) + tests + skill prompt si aplica.
   Seguir el patrón de `notes` (la más sencilla y completa).
   **Guía detallada paso a paso: `docs/adding-tools.md`.**
2. **Operación WRITE** → siempre par `propose_*` / `execute_*` con ActionProposal.
3. **Tests:** los unit tests mockean repositorios (`AsyncMock(spec=Repo)`).
   Ejecutar `pytest tests/unit/` antes de dar nada por terminado.
4. **Cambiar prompts/models/tool descriptions** = cambio evaluable (gobernanza).
   Anotarlo en el commit.
5. **Migraciones:** añadir a `migrations/init.sql` (idempotente, `IF NOT EXISTS`).
   Alembic se introducirá cuando haya necesidad real.
6. **Jerarquía de docs:** si algo contradice entre documentos, este fichero y
   `docs/architecture.md` mandan sobre el resto.