"""AncoraMind Agent — Agno agent creation and LLM model factory."""

import os

from agno.agent import Agent
from agno.db.postgres import PostgresDb
from agno.db.sqlite import SqliteDb
from agno.models.openai import OpenAIChat


def create_db(db_url: str | None = None):
    """Create the Agno runtime database.

    Uses PostgreSQL if AGNO_DATABASE_URL is set, otherwise defaults to SQLite.

    Args:
        db_url: PostgreSQL connection string, or None for SQLite default.
    """
    if db_url:
        return PostgresDb(db_url=db_url)

    # Default: SQLite for zero-config local development
    os.makedirs("tmp", exist_ok=True)
    return SqliteDb(
        session_table="ancoramind_sessions",
        db_file="tmp/ancoramind.db",
    )


def create_model(model_id: str = "gpt-4o", base_url: str | None = None) -> OpenAIChat:
    """Create the LLM model instance.

    Agno's OpenAIChat auto-detects OPENAI_API_KEY from the environment.

    Args:
        model_id: OpenAI model ID (e.g. "gpt-4o", "gpt-4o-mini").
        base_url: Optional custom base URL (e.g. for proxies / compatible APIs).

    Returns:
        Configured OpenAIChat model instance.
    """
    kwargs: dict = {"id": model_id}
    if base_url:
        kwargs["base_url"] = base_url
    return OpenAIChat(**kwargs)


def create_ancora_agent(
    model: OpenAIChat,
    tools: list,
    instructions: list[str],
    db=None,
) -> Agent:
    """Create the AncoraMind agent.

    Args:
        model: LLM model instance (OpenAIChat).
        tools: List of plain Python functions — Agno auto-converts to tools.
        instructions: List of instruction strings (one per markdown prompt file).
        db: Agno database for session persistence (PostgresDb or SqliteDb).

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