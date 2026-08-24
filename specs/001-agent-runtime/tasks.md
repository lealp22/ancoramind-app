# Tasks: 001 — Agent Runtime Functional

## Task Breakdown

### T1: Project scaffolding
- [x] Directory structure
- [x] pyproject.toml with dependencies
- [x] .env.example
- [x] Dockerfile + docker-compose.yml
- [x] Install dependencies in venv

### T2: Configuration
- [x] Implement `src/config.py` with Pydantic Settings
- [x] Load from `.env` file
- [x] Validate required fields on startup (TELEGRAM_TOKEN)

### T3: LLM Factory
- [x] Implement `create_model()` in `src/agent/ancora_agent.py`
- [x] Support OpenAI provider (OpenAIChat, auto-detects OPENAI_API_KEY)
- [x] Graceful error for missing/invalid API key

### T4: Agent Instructions
- [x] Implement `src/agent/instructions.py` to load markdown prompts
- [x] Assemble identity + soul + tool_contract + channel policy (4 blocks)
- [x] All prompt files loadable and tested

### T5: System Tool
- [x] Implement `get_current_datetime` in `src/agent/tools/system.py`
- [x] Plain Python function — Agno auto-converts to tool
- [x] ISO 8601 formatted datetime with timezone

### T6: Agent Creation
- [x] Implement `create_ancora_agent()` + `create_db()` + `create_model()`
- [x] SQLite (default) and PostgreSQL support
- [x] Agent parameters: history=10, datetime context, markdown

### T7: AgentOS + Telegram
- [x] Implement `src/main.py` with AgentOS + Telegram interface
- [x] Webhook at `/telegram/webhook`
- [x] Private chat filter (`reply_to_mentions_only`)
- [x] User allowlist support (`ALLOWED_TELEGRAM_USER_IDS`)

### T8: Docker
- [x] Dockerfile builds and runs
- [x] docker-compose with PostgreSQL profile
- [x] SQLite zero-config default for local dev

### T9: Manual E2E Test (requires real credentials)
- [ ] `TELEGRAM_TOKEN` from @BotFather
- [ ] `OPENAI_API_KEY`
- [ ] Start ngrok: `ngrok http 7777`
- [ ] Set webhook: `curl .../setWebhook?url=$NGROK_URL/telegram/webhook`
- [ ] `python -m src.main`
- [ ] Send "Hola" → respuesta coherente
- [ ] Send "¿Qué hora es?" → Tool llamada → hora correcta
- [ ] Multi-turn conversation → contexto mantenido

## Verification

- [x] `pytest tests/unit/` → **17 passed**
- [x] Tool execution verified (`get_current_datetime()` returns ISO 8601)
- [x] Agent instructions: 4 blocks loaded (identity, soul, tool_contract, telegram)
- [x] Config: all settings load from env vars with sensible defaults
- [x] Agent created successfully with model + db + tools + instructions
- [x] Spanish prompts and personality configured
- [ ] E2E Telegram test pending — requires real credentials