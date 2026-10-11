# AncoraMind

> **Personal AI assistant with operational memory.**
>
> POC/MVP — Agno + AgentOS + PostgreSQL + Telegram

---

## What is AncoraMind?

AncoraMind is a personal AI assistant that behaves like an **intelligent personal inbox with operational memory**.

You tell it things. It remembers, organizes, retrieves, and acts — without you needing to decide which app, table, category, or workflow to use.

```
User sends a workshop invoice
        ↓
AncoraMind receives, stores, analyzes
        ↓
Extracts: date, mileage, amount, work performed
        ↓
Proposes: register maintenance, create reminder
        ↓
User confirms
        ↓
Canonical data persisted with full provenance
```

---

## Architecture

```
Telegram → admission / idempotency → AgentOS → governed agent → Tools → AncoraMind Core → PostgreSQL
```

See [docs/architecture.md](docs/architecture.md) for full details.

### Key principles

- **Single primary agent** — add capability ≈ add Tool
- **Agent Runtime ≠ Core** — Agno is replaceable infrastructure; Core is the product
- **Probabilistic / Deterministic boundary** — LLM decides which capability; Core decides permissions
- **Canonical memory** — PostgreSQL is the source of truth, not conversation memory
- **Governed mutations** — WRITE and EXTERNAL_ACTION operations require an ActionProposal and human confirmation
- **Governed inference** — model access is budgeted, auditable, and routed through versioned runtime configuration

---

## Quick Start

```bash
# Clone and setup
git clone <repo-url>
cd ancoramind-app

# Copy environment config
cp .env.example .env
# Edit .env with your LLM and Telegram credentials

# Install development dependencies
pip install -e ".[dev]"

# Optional: start local PostgreSQL when .env uses the local backend
docker compose --profile postgres up -d postgres

# Start the application
python -m src.main
```

For daily startup, Supabase-backed setups, Telegram webhook configuration, and
Railway deployment, see [Quick Start](docs/quick-start.md) and
[E2E Deployment](docs/deployment-e2e.md).

---

## Documentation

| Document | Description |
|---|---|
| [Architecture](docs/architecture.md) | Full architecture reference |
| [Governance](docs/governance.md) | AI governance policies |
| [ADR-001](docs/adr/ADR-001-agno-runtime.md) | Agno runtime decision |
| [Spec-013](specs/013-llm-access-governance/spec.md) | Governed LLM access, Telegram admission and observability target |
| [ADR-004](docs/adr/ADR-004-telegram-admission-at-most-once.md) | Telegram idempotency and at-most-once Agent execution |
| [ADR-005](docs/adr/ADR-005-governed-llm-access-runtime-config.md) | Runtime model configuration and LiteLLM Gateway |
| [ADR-006](docs/adr/ADR-006-opentelemetry-observability.md) | OpenTelemetry and Grafana Cloud observability |
| [Development](docs/development.md) | Local development guide |
| [Adding Tools](docs/adding-tools.md) | Capability/tool implementation guide |
| [Quick Start](docs/quick-start.md) | Guía de arranque rápido diario |
| [E2E Deployment](docs/deployment-e2e.md) | Step-by-step Telegram + PostgreSQL deployment |
| [Railway Deployment](docs/deployment-railway.md) | Railway + GitHub CI/CD + stable Telegram webhook |
| [Operational Runbooks](docs/runbooks-013.md) | Triage, LiteLLM Gateway, circuit breaker, budgets and incident recovery |
| [Spec-020](specs/020-mypy-ci-gate/spec.md) | Strict `mypy src/` quality gate in CI |

---

## Tech Stack

| Component | Technology |
|---|---|
| Agent Runtime | Agno + AgentOS |
| Language | Python 3.12+ |
| Database | PostgreSQL |
| Channel | Telegram (private chats) |
| Validation | Pydantic |
| LLM Access | Governed `LLMAccess` with runtime snapshots, budgets, cost ledger and versioned LiteLLM Gateway aliases |
| Observability | Metadata-only OpenTelemetry; private Collector/Grafana rollout prepared |
| Deployment | Docker local; Railway prepared for managed deployment |
| Quality | GitHub Actions: Ruff, strict `mypy src/`, unit tests, integration tests, and Collector-config validation |

---

## Project Structure

```
src/
├── agent/          ← Agno integration (infrastructure)
├── domain/         ← Business logic (product)
├── repositories/   ← PostgreSQL access
├── storage/        ← Document storage abstraction
├── security/       ← Identity, authorization, policy
├── notifications/  ← Telegram delivery and safe markup rendering
└── governance/     ← Metadata, risk, audit

prompts/            ← Versioned AI assets
specs/              ← Spec-driven development
evals/              ← Agentic evaluations
docs/               ← Architecture, governance, ADRs
gateway/            ← LiteLLM Proxy pilot configuration
observability/      ← Private OpenTelemetry Collector configuration
```

---

## Development Status

- [x] Architecture & governance docs
- [x] M1: Agent Runtime functional (Telegram + Agno + AgentOS + session)
- [x] M2: Canonical Memory (PostgreSQL domain schema)
- [x] M3: Document Memory (attachment → storage → extraction)
- [x] M4: Vehicle Vertical Slice (invoice → maintenance → query)
- [x] M5: Calendar & Reminders
- [x] BL-21: Multi-list TODOs with governed mutations
- [x] Strict static quality gate: Ruff + `mypy src/` in GitHub Actions
- [x] BL-23 T2–T14: governed LLM access, durable admission, execution budget,
      document extraction port, metadata-only OpenTelemetry, the LiteLLM
      Gateway pilot, cost/reliability governance (circuit breaker, rate
      limits, spend budgets with run-start hard stop), hot model change via
      additive versioned Gateway aliases, and local hardening
      (load/crash/retention suite + operational runbooks) (Railway rollout of
      Collector/Grafana/LiteLLM, benchmark with a real key and E2E remain pending;
      BL-23 stays open)
- [ ] MVP: Usable personal assistant (complete Telegram E2E validation remains)

### Capabilities (Agent reads/proposes; Core executes)

| Domain | Tools | Risk |
|---|---|---|
| System | `get_current_datetime` | READ |
| Notes | `propose_note`, `search_notes` | WRITE/READ |
| Documents | `search_documents`, `search_documents_semantically`, `get_document`, `analyze_document`, `propose_document_delete`, `export_document` | READ/EXTRACT/DESTRUCTIVE/EXPORT |
| Vehicles | `find_vehicle`, `get_vehicle_summary`, `get_vehicle_maintenance_history` | READ |
| Vehicles (creation) | `propose_vehicle` | WRITE |
| Vehicles (write) | `propose_vehicle_maintenance` | WRITE |
| Reminders | `list_reminders`, `propose_reminder`, `propose_reminder_snooze` | READ/WRITE |
| Calendar | `check_calendar`, `propose_calendar_event` | READ/EXTERNAL_ACTION |
| TODO lists | `list_todo_lists`, `propose_todo_list`, `propose_todo_list_rename`, `propose_todo_list_delete` | READ/WRITE/DESTRUCTIVE |
| TODO items | `list_todo_items`, `propose_todo_item`, `propose_todo_item_update`, `propose_todo_item_complete`, `propose_todo_item_reopen`, `propose_todo_item_move`, `propose_todo_item_delete` | READ/WRITE/DESTRUCTIVE |

> All WRITE, EXTERNAL_ACTION, and DESTRUCTIVE operations use ActionProposal governance:
> propose → Core-verified human consent → atomic Core execution → audit.
> No `execute_*` tool is exposed to the Agent. With governed consent disabled,
> proposals stay pending; the legacy LLM confirmation path is retired (2026-10-11).
> This local hardening still requires controlled rollout and Telegram E2E.

Without `ANCORA_DATABASE_URL`, the application starts in a degraded mode with
domain DB tools omitted; system time and separately configured export/web search
remain available.

### Quality checks

```bash
ruff check src/ tests/ scripts/ migrations/
mypy src/
pytest tests/unit/ -q
pytest tests/integration/ -q  # Requires Docker/PostgreSQL
```

GitHub Actions runs Ruff and strict `mypy src/` before the unit suite, plus
separate integration and OpenTelemetry Collector configuration jobs.

---

## License

Proprietary — POC/MVP stage.
