# Design: 001 — Agent Runtime Functional

## Architecture Overview

```
Telegram webhook → AgentOS Telegram Interface → AgentOS → AncoraMind Agent → LLM → response
                                                                         ↓
                                                                   get_current_datetime Tool
```

## Components

### 1. Configuration (`src/config.py`)

```python
class Settings(BaseSettings):
    # LLM
    llm_provider: str
    llm_model: str
    llm_api_key: SecretStr
    llm_base_url: str | None = None

    # Telegram
    telegram_bot_token: SecretStr
    allowed_telegram_user_ids: list[int] = []

    # Database (Agno runtime)
    database_url: str

    # App
    app_env: str = "development"
    app_debug: bool = False
```

### 2. Agent Instructions (`src/agent/instructions.py`)

Carga y ensambla el context del agente desde los archivos en `prompts/`:
- `identity.md`
- `soul.md`
- `tool_contract.md`
- `channels/telegram.md`

### 3. AncoraMind Agent (`src/agent/ancora_agent.py`)

```python
def create_ancora_agent(
    model,
    db,
    tools: list,
    instructions: str,
) -> Agent:
    return Agent(
        name="AncoraMind",
        model=model,
        db=db,
        tools=tools,
        instructions=instructions,
        add_history_to_context=True,
        markdown=True,
    )
```

### 4. System Tool (`src/agent/tools/system.py`)

```python
@tool
def get_current_datetime() -> str:
    """Returns the current date and time."""
    return datetime.now().isoformat()
```

### 5. AgentOS Setup (`src/main.py`)

```python
def main():
    settings = Settings()
    model = create_model(settings)
    db = create_runtime_db(settings)

    agent = create_ancora_agent(
        model=model,
        db=db,
        tools=[get_current_datetime],
        instructions=assemble_instructions(),
    )

    agent_os = AgentOS(
        agents=[agent],
        interfaces=[
            Telegram(
                agent=agent,
                bot_token=settings.telegram_bot_token.get_secret_value(),
            )
        ],
    )

    agent_os.serve()
```

### 6. LLM Factory (`src/agent/ancora_agent.py`)

```python
def create_model(settings: Settings):
    provider = settings.llm_provider.lower()

    if provider == "openai":
        return OpenAIChat(
            id=settings.llm_model,
            api_key=settings.llm_api_key.get_secret_value(),
        )
    elif provider == "anthropic":
        return Claude(
            id=settings.llm_model,
            api_key=settings.llm_api_key.get_secret_value(),
        )
    # ... additional providers
```

## Database

Solo se usa PostgreSQL para el runtime de Agno (schema `agno_runtime`).
No se crean tablas en schema `ancora` en este milestone.

## Security

- Solo private chats (filtrar en Telegram interface o middleware)
- Allowlist de user IDs
- Secrets via environment variables
- No user context resolution todavía (se añadirá en milestones posteriores)

## Error Handling

- LLM connection errors → log + graceful degradation
- Telegram API errors → log + retry
- Tool execution errors → return structured error to agent