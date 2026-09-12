"""AncoraMind — Application entry point.

Orchestrates Agno + AgentOS + Telegram + reminder worker.
Run: python -m src.main
"""

import logging
import os
import sys
from typing import Any

from agno.os.app import AgentOS
from agno.os.interfaces.telegram import Telegram
from fastapi import FastAPI

from src.agent.ancora_agent import (
    create_ancora_agent,
    create_db,
    create_model_from_settings,
)
from src.agent.instructions import assemble_instructions
from src.agent.lifecycle import install_reminder_worker_lifespan
from src.agent.server import resolve_server_config
from src.agent.tools.system import get_current_datetime
from src.config import Settings

logger = logging.getLogger(__name__)

# ── Optional domain tools (require ANCORA_DATABASE_URL) ──
_NOTE_TOOLS: list[Any] = []

def _init_domain_tools(settings: Settings) -> list[Any]:
    """Initialize domain tools if the domain database is configured.

    Domain tools (notes, vehicles, etc.) require ANCORA_DATABASE_URL.
    If not set, they are silently skipped.
    """
    tools: list[Any] = []

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

        from src.agent.tools.calendar import (
            check_calendar,
            execute_calendar_event,
            propose_calendar_event,
        )
        from src.agent.tools.reminders import (
            execute_reminder,
            list_reminders,
            propose_reminder,
        )

        tools.extend([
            list_reminders, propose_reminder, execute_reminder,
            check_calendar, propose_calendar_event, execute_calendar_event,
        ])
        logger.info(
            "Reminder + Calendar tools registered: list/propose/execute_reminder, "
            "check_calendar, propose/execute_calendar_event"
        )

        from src.agent.tools.todos import (
            execute_todo_item,
            execute_todo_list,
            list_todo_items,
            list_todo_lists,
            propose_todo_item,
            propose_todo_item_complete,
            propose_todo_item_delete,
            propose_todo_item_move,
            propose_todo_item_reopen,
            propose_todo_item_update,
            propose_todo_list,
            propose_todo_list_delete,
            propose_todo_list_rename,
        )

        tools.extend([
            list_todo_lists, propose_todo_list, execute_todo_list,
            propose_todo_list_rename, propose_todo_list_delete,
            list_todo_items, propose_todo_item, propose_todo_item_update,
            propose_todo_item_complete, propose_todo_item_reopen,
            propose_todo_item_move, propose_todo_item_delete, execute_todo_item,
        ])
        logger.info(
            "Todo tools registered: list/propose/execute_todo_list (+rename/delete), "
            "list/propose/execute_todo_item (+update/complete/reopen/move/delete)"
        )

    except Exception:
        logger.warning(
            "Failed to initialize domain database — "
            "domain tools will not be available",
            exc_info=True,
        )

    return tools


def _register_reminder_worker(app: FastAPI, settings: Settings) -> None:
    """Install the auto-gated reminder-worker FastAPI lifespan (BL-22)."""
    install_reminder_worker_lifespan(app, settings)


def create_app() -> tuple[FastAPI, AgentOS]:
    """Build the AgentOS application with AncoraMind agent and Telegram interface."""
    settings = Settings()

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
    model = create_model_from_settings(settings)
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
        tool_call_limit=settings.agent_tool_call_limit,
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
                reply_to_mentions_only=bool(allowlist),
                reply_to_bot_messages=False,
            )
        ],
    )

    app = agent_os.get_app()
    logger.info("AgentOS app created — webhook: /telegram/webhook")

    # ── Reminder worker (BL-5) ─────────────────────────
    _register_reminder_worker(app, settings)

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

    settings = Settings()
    server = resolve_server_config(settings.app_env, os.environ)
    logger.info(
        "Starting HTTP server — host: %s | port: %d | reload: %s",
        server.host,
        server.port,
        server.reload,
    )
    # Uvicorn requires an import string when reload is enabled. In production,
    # pass the already-created app to avoid constructing it a second time.
    serve_app = "src.main:app" if server.reload else app
    agent_os.serve(
        app=serve_app,
        host=server.host,
        port=server.port,
        reload=server.reload,
    )


if __name__ == "__main__":
    main()
