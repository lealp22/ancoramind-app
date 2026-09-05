"""AncoraMind — Application entry point.

Orchestrates Agno + AgentOS + Telegram.
Run: python -m src.main
"""

import logging
import os
import sys

from agno.os.app import AgentOS
from agno.os.interfaces.telegram import Telegram

from src.agent.ancora_agent import create_ancora_agent, create_db, create_model
from src.agent.instructions import assemble_instructions
from src.agent.tools.system import get_current_datetime
from src.config import Settings

logger = logging.getLogger(__name__)

# ── Optional domain tools (require ANCORA_DATABASE_URL) ──
_NOTE_TOOLS: list = []


def _init_domain_tools(settings: Settings) -> list:
    """Initialize domain tools if the domain database is configured.

    Domain tools (notes, vehicles, etc.) require ANCORA_DATABASE_URL.
    If not set, they are silently skipped.
    """
    tools: list = []

    if not settings.ancora_database_url:
        logger.info(
            "ANCORA_DATABASE_URL not set — domain tools skipped "
            "(notes, vehicles, etc.)"
        )
        return tools

    try:
        from src.repositories.database import init_database

        # initialize_db is sync (just creates engine, doesn't connect)
        init_database(
            database_url=settings.ancora_database_url,
            echo=settings.app_debug,
        )
        logger.info("Domain database initialized")

        from src.agent.tools.notes import remember_note, search_notes

        tools.extend([remember_note, search_notes])
        _NOTE_TOOLS.extend([remember_note, search_notes])
        logger.info("Note tools registered: remember_note, search_notes")

        from src.agent.tools.documents import (
            analyze_document,
            get_document,
            search_documents,
        )

        tools.extend([search_documents, get_document, analyze_document])
        logger.info(
            "Document tools registered: "
            "search_documents, get_document, analyze_document"
        )

        from src.agent.tools.maintenance import (
            execute_vehicle_maintenance,
            propose_vehicle_maintenance,
        )
        from src.agent.tools.vehicles import (
            execute_vehicle,
            find_vehicle,
            get_vehicle_maintenance_history,
            get_vehicle_summary,
            propose_vehicle,
        )

        tools.extend([
            find_vehicle, get_vehicle_summary, get_vehicle_maintenance_history,
            propose_vehicle, execute_vehicle,
            propose_vehicle_maintenance, execute_vehicle_maintenance,
        ])
        logger.info(
            "Vehicle tools registered: find_vehicle, get_vehicle_summary, "
            "get_vehicle_maintenance_history, propose/execute_vehicle, "
            "propose/execute_vehicle_maintenance"
        )

        from src.agent.tools.reminders import (
            execute_reminder,
            list_reminders,
            propose_reminder,
        )
        from src.agent.tools.calendar import (
            check_calendar,
            execute_calendar_event,
            propose_calendar_event,
        )

        tools.extend([
            list_reminders, propose_reminder, execute_reminder,
            check_calendar, propose_calendar_event, execute_calendar_event,
        ])
        logger.info(
            "Reminder + Calendar tools registered: list/propose/execute_reminder, "
            "check_calendar, propose/execute_calendar_event"
        )

    except Exception:
        logger.warning(
            "Failed to initialize domain database — "
            "domain tools will not be available",
            exc_info=True,
        )

    return tools


def create_app():
    """Build the AgentOS application with AncoraMind agent and Telegram interface."""
    settings = Settings()  # type: ignore[call-arg]

    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    logger.info("Starting AncoraMind — env: %s", settings.app_env)

    # ── Validate required config ──────────────────────
    if not settings.telegram_token:
        logger.error("TELEGRAM_TOKEN is required. Set it in .env or environment.")
        sys.exit(1)

    # ── Database (Agno runtime) ───────────────────────
    db = create_db(db_url=settings.db_url)
    if settings.db_url:
        logger.info("Using PostgreSQL for Agno runtime")
    else:
        logger.info("Using SQLite for Agno runtime (tmp/ancoramind.db)")

    # ── LLM Model ─────────────────────────────────────
    api_key = None
    if settings.llm_provider == "openrouter" and settings.openrouter_api_key:
        api_key = settings.openrouter_api_key
    elif settings.llm_provider == "openai" and settings.openai_api_key:
        api_key = settings.openai_api_key

    model = create_model(
        provider=settings.llm_provider,
        model_id=settings.llm_model,
        base_url=settings.llm_base_url,
        api_key=api_key,
    )
    logger.info("LLM provider: %s | model: %s", settings.llm_provider, settings.llm_model)

    # ── Agent Instructions ────────────────────────────
    instructions = assemble_instructions()
    logger.info("Loaded %d instruction blocks", len(instructions))

    # ── Tools ─────────────────────────────────────────
    tools = [get_current_datetime]
    tools.extend(_init_domain_tools(settings))
    logger.info("Total tools: %d — %s", len(tools), [t.__name__ for t in tools])

    # ── AncoraMind Agent ──────────────────────────────
    ancora_agent = create_ancora_agent(
        model=model,
        db=db,
        tools=tools,
        instructions=instructions,
    )
    logger.info("AncoraMind agent created")

    # ── AgentOS + Telegram ────────────────────────────
    allowlist = settings.allowed_user_ids
    agent_os = AgentOS(
        agents=[ancora_agent],
        db=db,
        interfaces=[
            Telegram(
                agent=ancora_agent,
                reply_to_mentions_only=True if allowlist else False,
            )
        ],
    )

    app = agent_os.get_app()
    logger.info("AgentOS app created — webhook: /telegram/webhook")

    return app, agent_os


# Module-level app for AgentOS serve (string reference: "src.main:app")
try:
    app, agent_os = create_app()
except ValueError as e:
    if "Token must contain a colon" in str(e):
        print(
            "❌ TELEGRAM_TOKEN is not a valid Telegram bot token.\n"
            "   Get one from @BotFather on Telegram.\n"
            "   Format: 123456789:ABCdefGHIjklMNOpqrsTUVwxyz\n"
            f"\n   Error: {e}",
            file=sys.stderr,
        )
        sys.exit(1)
    raise
except Exception:
    logging.exception("Failed to create app")
    raise


def main() -> None:
    """Start AncoraMind with AgentOS + Telegram."""
    if os.environ.get("NGROK_URL"):
        ngrok_url = os.environ["NGROK_URL"]
        logger.info("ngrok tunnel: %s", ngrok_url)
        logger.info(
            "Register webhook: "
            "curl https://api.telegram.org/bot${TELEGRAM_TOKEN}/"
            "setWebhook?url=%s/telegram/webhook",
            ngrok_url,
        )

    agent_os.serve(app="src.main:app", reload=True)


if __name__ == "__main__":
    main()