# AncoraMind — Local Development Guide

## Prerequisites

- Python 3.12+
- PostgreSQL 16+
- Docker & Docker Compose
- Telegram Bot Token (from @BotFather)

## Setup

```bash
# Clone
git clone <repo-url>
cd ancoramind-core

# Virtual environment
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# Install dependencies
pip install -e ".[dev]"

# Environment
cp .env.example .env
# Edit .env with your values

# Database
docker compose up -d postgres
alembic upgrade head

# Run
python -m src.main
```

## Running with Docker

```bash
docker compose up -d
```

## Testing

```bash
# Unit tests
pytest tests/unit/

# Integration tests (requires PostgreSQL)
pytest tests/integration/

# E2E tests (requires full stack)
pytest tests/e2e/

# Evals
pytest evals/
```

## Environment Variables

See `.env.example` for all required variables.

Key variables:
- `LLM_PROVIDER` — e.g. `openai`, `anthropic`
- `LLM_MODEL` — e.g. `gpt-4o`
- `LLM_API_KEY` — your API key
- `TELEGRAM_BOT_TOKEN` — from @BotFather
- `DATABASE_URL` — PostgreSQL connection string
- `ALLOWED_TELEGRAM_USER_IDS` — comma-separated list

## Project Conventions

- **No Agno inheritance in domain code** — domain services are plain Python
- **Tools are thin adapters** — they call domain services, never contain business logic
- **Parameterized queries only** — no string interpolation in SQL
- **User context from runtime, never from LLM**
- **Prompts in Git, not in code strings**