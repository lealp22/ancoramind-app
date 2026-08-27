"""AncoraMind Agent — Agno agent creation and LLM model factory.

Supports multiple LLM providers:
- openai:     OpenAIChat (uses OPENAI_API_KEY)
- openrouter: OpenRouter (uses OPENROUTER_API_KEY)
- openai-like: Generic OpenAI-compatible (uses OPENAI_API_KEY + custom base_url)
"""

import os

from agno.agent import Agent
from agno.db.postgres import PostgresDb
from agno.db.sqlite import SqliteDb


def create_db(db_url: str | None = None):
    """Create the Agno runtime database.

    Uses PostgreSQL if AGNO_DATABASE_URL is set, otherwise defaults to SQLite.
    """
    if db_url:
        return PostgresDb(db_url=db_url)
    os.makedirs("tmp", exist_ok=True)
    return SqliteDb(
        session_table="ancoramind_sessions",
        db_file="tmp/ancoramind.db",
    )


def create_model(
    provider: str = "openai",
    model_id: str = "gpt-5.4-mini",
    base_url: str | None = None,
    api_key: str | None = None,
):
    """Create the LLM model instance for the configured provider.

    Providers:
        openai:      OpenAIChat  — uses OPENAI_API_KEY env var
        openrouter:  OpenRouter  — uses OPENROUTER_API_KEY env var
        openai-like: OpenAILike  — uses OPENAI_API_KEY + custom base_url
                                   (Groq, Together, DeepSeek, Ollama, etc.)

    Args:
        provider: One of "openai", "openrouter", "openai-like".
        model_id: Model ID (e.g. "gpt-5.4-mini", "anthropic/claude-3.5-sonnet").
        base_url: Custom base URL (required for openai-like).
        api_key: Optional API key override (otherwise from env vars).

    Returns:
        Configured model instance.
    """
    provider = provider.lower().strip()

    if provider == "openai":
        from agno.models.openai import OpenAIChat

        kwargs: dict = {"id": model_id}
        if api_key:
            kwargs["api_key"] = api_key
        if base_url:
            kwargs["base_url"] = base_url
        return OpenAIChat(**kwargs)

    if provider == "openrouter":
        from agno.models.openrouter import OpenRouter

        kwargs = {"id": model_id}
        if api_key:
            kwargs["api_key"] = api_key
        if base_url:
            kwargs["base_url"] = base_url
        return OpenRouter(**kwargs)

    if provider == "openai-like":
        from agno.models.openai import OpenAILike

        if not base_url:
            raise ValueError(
                "LLM_BASE_URL is required when LLM_PROVIDER=openai-like. "
                "Example: https://api.groq.com/openai/v1"
            )
        kwargs = {"id": model_id, "base_url": base_url}
        if api_key:
            kwargs["api_key"] = api_key
        return OpenAILike(**kwargs)

    raise ValueError(
        f"Unsupported LLM_PROVIDER: {provider!r}. "
        "Use one of: openai, openrouter, openai-like"
    )


def create_ancora_agent(
    model,
    tools: list,
    instructions: list[str],
    db=None,
) -> Agent:
    """Create the AncoraMind agent.

    Args:
        model: LLM model instance (OpenAIChat, OpenRouter, or OpenAILike).
        tools: List of plain Python functions — Agno auto-converts to tools.
        instructions: List of instruction strings (one per markdown prompt file).
        db: Agno database for session persistence.

    Returns:
        Configured Agno Agent instance.
    """
    return Agent(
        name="AncoraMind",
        model=model,
        db=db,
        tools=tools,
        instructions=instructions,
        add_history_to_context=True,
        num_history_runs=10,
        add_datetime_to_context=True,
        markdown=True,
        description=(
            "AncoraMind — tu asistente personal inteligente con memoria operativa."
        ),
    )