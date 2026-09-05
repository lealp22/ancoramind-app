# AncoraMind — Local Development Guide

> Comandos multi-shell: los que usan `<` (redirección bash) no funcionan en
> PowerShell — se indica la alternativa cuando aplica.
> Arranque día a día: ver [quick-start.md](quick-start.md). Primera vez:
> ver [deployment-e2e.md](deployment-e2e.md).

## Prerequisites

- Python 3.12+
- Docker & Docker Compose (PostgreSQL 16)
- ngrok (para el webhook de Telegram en local)
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

## Database (PostgreSQL via Docker)

```bash
# Arrancar solo PostgreSQL
docker compose up postgres -d
# Parar
docker compose down
```

### Aplicar migraciones

Migraciones idempotentes en `migrations/init.sql` (schema `ancora`, 9 tablas).
No se usa Alembic de momento (se introducirá cuando haya necesidad real).

```bash
# PowerShell:
Get-Content migrations/init.sql | docker compose exec -T postgres psql -U ancora -d ancoramind

# Git Bash:
docker compose exec -T postgres psql -U ancora -d ancoramind < migrations/init.sql
```

## Run

```bash
python -m src.main
```

Requiere: `.env` con `TELEGRAM_TOKEN`, ngrok corriendo y webhook registrado
(pasos 2–3 de [quick-start.md](quick-start.md)). Sin `ANCORA_DATABASE_URL` la
app arranca igualmente pero sin domain tools (degradación graceful).

## Testing

```bash
# Unit tests (68 passing — repos mockeados, sin PostgreSQL)
pytest tests/unit/

# Integration tests (requiere PostgreSQL real — pendiente, ver BACKLOG.md BL-2)
pytest tests/integration/

# E2E tests (requiere stack completo)
pytest tests/e2e/
```

## Lint / Type check

```bash
ruff check src/
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
| `LLM_MODEL` | Modelo | `gpt-5.4-mini` |
| `LLM_BASE_URL` | Endpoint custom (obligatorio en `openai-like`) | — |
| `TELEGRAM_TOKEN` | Token del bot (de @BotFather) | — |
| `NGROK_URL` | URL del túnel para el webhook | — |
| `AGNO_DATABASE_URL` | Runtime de Agno (si no: SQLite en `tmp/`) | — |
| `ANCORA_DATABASE_URL` | DB del dominio (schema `ancora`) — sin ella, sin domain tools | — |
| `DOCUMENT_STORAGE_PATH` | Ruta del storage de documentos | `./data/documents` |
| `ALLOWED_TELEGRAM_USER_IDS` | Allowlist de user IDs (coma-separados) | vacío = todos |
| `LOG_LEVEL` | Nivel de logging | `INFO` |
| `APP_DEBUG` | Debug (echo de SQL) | `false` |

## Project Conventions

- **No Agno inheritance in domain code** — domain services are plain Python
  (única excepción documentada: extracción IA en `domain/documents/service.py`)
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