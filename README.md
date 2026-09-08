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
Telegram → Agno AgentOS → AncoraMind Agent → Tools → AncoraMind Core → PostgreSQL
```

See [docs/architecture.md](docs/architecture.md) for full details.

### Key principles

- **Single primary agent** — add capability ≈ add Tool
- **Agent Runtime ≠ Core** — Agno is replaceable infrastructure; Core is the product
- **Probabilistic / Deterministic boundary** — LLM decides which capability; Core decides permissions
- **Canonical memory** — PostgreSQL is the source of truth, not conversation memory

---

## Quick Start

```bash
# Clone and setup
git clone <repo-url>
cd ancoramind-core

# Copy environment config
cp .env.example .env
# Edit .env with your LLM and Telegram credentials

# Start with Docker
docker compose up -d
```

---

## Documentation

| Document | Description |
|---|---|
| [Architecture](docs/architecture.md) | Full architecture reference |
| [Governance](docs/governance.md) | AI governance policies |
| [ADR-001](docs/adr/ADR-001-agno-runtime.md) | Agno runtime decision |
| [Development](docs/development.md) | Local development guide |
| [Quick Start](docs/quick-start.md) | Guía de arranque rápido diario |
| [E2E Deployment](docs/deployment-e2e.md) | Step-by-step Telegram + PostgreSQL deployment |
| [Railway Deployment](docs/deployment-railway.md) | Railway + GitHub CI/CD + stable Telegram webhook |

---

## Tech Stack

| Component | Technology |
|---|---|
| Agent Runtime | Agno + AgentOS |
| Language | Python 3.12+ |
| Database | PostgreSQL |
| Channel | Telegram (private chats) |
| Validation | Pydantic |
| Deployment | Docker local; Railway prepared for managed deployment |

---

## Project Structure

```
src/
├── agent/          ← Agno integration (infrastructure)
├── domain/         ← Business logic (product)
├── services/       ← Application services
├── repositories/   ← PostgreSQL access
├── storage/        ← Document storage abstraction
├── security/       ← Identity, authorization, policy
└── governance/     ← Metadata, risk, audit

prompts/            ← Versioned AI assets
specs/              ← Spec-driven development
evals/              ← Agentic evaluations
docs/               ← Architecture, governance, ADRs
```

---

## Development Status

- [x] Architecture & governance docs
- [x] M1: Agent Runtime functional (Telegram + Agno + AgentOS + session)
- [x] M2: Canonical Memory (PostgreSQL domain schema)
- [x] M3: Document Memory (attachment → storage → extraction)
- [x] M4: Vehicle Vertical Slice (invoice → maintenance → query)
- [x] M5: Calendar & Reminders
- [ ] MVP: Usable personal assistant (E2E Telegram validation)

### Capabilities (19 tools)

| Domain | Tools | Risk |
|---|---|---|
| System | `get_current_datetime` | READ |
| Notes | `remember_note`, `search_notes` | WRITE/READ |
| Documents | `search_documents`, `get_document`, `analyze_document` | READ/EXTRACT |
| Vehicles | `find_vehicle`, `get_vehicle_summary`, `get_vehicle_maintenance_history` | READ |
| Vehicles (creation) | `propose_vehicle`, `execute_vehicle` | WRITE |
| Vehicles (write) | `propose_vehicle_maintenance`, `execute_vehicle_maintenance` | WRITE |
| Reminders | `list_reminders`, `propose_reminder`, `execute_reminder` | READ/WRITE |
| Calendar | `check_calendar`, `propose_calendar_event`, `execute_calendar_event` | READ/EXTERNAL_ACTION |

> WRITE / EXTERNAL_ACTION operations use ActionProposal governance:
> propose → user confirmation → execute → audit.

---

## License

Proprietary — POC/MVP stage.