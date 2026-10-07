"""AncoraMind — Application entry point.

Orchestrates Agno + AgentOS + Telegram + reminder worker.
Run: python -m src.main
"""

import logging
import os
import sys
from typing import Any

# Must be set before importing Agno so local execution has the same privacy
# posture as the Docker image (specs/013 T10).
# IMPORTANT: this must stay above the Agno imports below (import-time
# side effect). Ruff's isort (rule I) will not reorder across this
# assignment, but any manual edit or unrelated tool that reformats this
# import block must preserve the ordering, or Agno telemetry will be
# initialized before this override takes effect.
os.environ["AGNO_TELEMETRY"] = "false"

from agno.os.app import AgentOS
from agno.os.interfaces.base import BaseInterface
from agno.os.interfaces.telegram import Telegram
from agno.os.settings import AgnoAPISettings
from fastapi import FastAPI

from src.agent.admin_dashboard import (
    install_admin_dashboard,
    validate_admin_dashboard_settings,
)
from src.agent.agent_os_rest_guard import install_agent_os_rest_guard
from src.agent.ancora_agent import (
    create_ancora_agent,
    create_db,
    create_model_from_settings,
)
from src.agent.health import HealthRegistry, install_health_readiness_endpoint
from src.agent.instructions import assemble_instructions
from src.agent.lifecycle import (
    install_health_signals_lifespan,
    install_interaction_processor_lifespan,
    install_observability_lifespan,
    install_reminder_worker_lifespan,
    install_runtime_config_manager_lifespan,
)
from src.agent.runtime_config_admin import (
    create_runtime_config_manager,
    install_runtime_config_admin_api,
    validate_runtime_config_admin_settings,
)
from src.agent.server import resolve_server_config
from src.agent.telegram_admission import (
    install_telegram_admission_endpoint,
    validate_telegram_admission_settings,
    validate_webhook_secret_settings,
)
from src.agent.telegram_pairing_admin import (
    install_telegram_pairing_admin_api,
    validate_telegram_pairing_admin_settings,
)
from src.agent.tools.system import get_current_datetime
from src.config import Settings
from src.domain.runtime_config.service import RuntimeConfigManager
from src.observability import configure_observability
from src.repositories.database import get_session

logger = logging.getLogger(__name__)


def _init_domain_tools(settings: Settings) -> list[Any]:
    """Initialize domain tools if the domain database is configured.

    Domain tools (notes, vehicles, etc.) require ANCORA_DATABASE_URL.
    If not set, they are silently skipped.
    """
    tools: list[Any] = []

    if settings.web_search_enabled:
        from src.agent.tools.web_search import configure_web_search, search_web

        configure_web_search(settings)
        tools.append(search_web)
        logger.info("Governed public web-search tool registered: search_web (provider=tavily)")

    if not settings.ancora_database_url:
        logger.info(
            "ANCORA_DATABASE_URL not set — database domain tools skipped "
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

        from src.agent.tools.notes import execute_note, propose_note, search_notes

        tools.extend([propose_note, execute_note, search_notes])
        logger.info("Note tools registered: propose_note, execute_note, search_notes")

        from src.agent.tools.documents import (
            analyze_document,
            execute_document_delete,
            get_document,
            propose_document_delete,
            search_documents,
            search_documents_semantically,
        )

        tools.extend(
            [
                search_documents,
                search_documents_semantically,
                get_document,
                analyze_document,
                propose_document_delete,
                execute_document_delete,
            ]
        )
        logger.info(
            "Document tools registered: search_documents, search_documents_semantically, "
            "get_document, analyze_document, "
            "propose_document_delete, execute_document_delete"
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

        tools.extend(
            [
                find_vehicle,
                get_vehicle_summary,
                get_vehicle_maintenance_history,
                propose_vehicle,
                execute_vehicle,
                propose_vehicle_maintenance,
                execute_vehicle_maintenance,
            ]
        )
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
            execute_reminder_snooze,
            list_reminders,
            propose_reminder,
            propose_reminder_snooze,
        )

        tools.extend(
            [
                list_reminders,
                propose_reminder,
                execute_reminder,
                propose_reminder_snooze,
                execute_reminder_snooze,
                check_calendar,
                propose_calendar_event,
                execute_calendar_event,
            ]
        )
        logger.info(
            "Reminder + Calendar tools registered: list/propose/execute_reminder, "
            "propose/execute_reminder_snooze, check_calendar, "
            "propose/execute_calendar_event"
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

        tools.extend(
            [
                list_todo_lists,
                propose_todo_list,
                execute_todo_list,
                propose_todo_list_rename,
                propose_todo_list_delete,
                list_todo_items,
                propose_todo_item,
                propose_todo_item_update,
                propose_todo_item_complete,
                propose_todo_item_reopen,
                propose_todo_item_move,
                propose_todo_item_delete,
                execute_todo_item,
            ]
        )
        logger.info(
            "Todo tools registered: list/propose/execute_todo_list (+rename/delete), "
            "list/propose/execute_todo_item (+update/complete/reopen/move/delete)"
        )

    except Exception:
        logger.warning(
            "Failed to initialize domain database — domain tools will not be available",
            exc_info=True,
        )

    return tools


def _register_reminder_worker(
    app: FastAPI, settings: Settings, health_registry: HealthRegistry
) -> None:
    """Install the auto-gated reminder-worker FastAPI lifespan (BL-22)."""
    install_reminder_worker_lifespan(app, settings, health_registry=health_registry)


def _register_interaction_processor(
    app: FastAPI,
    settings: Settings,
    *,
    db: Any,
    tools: list[Any],
    instructions: list[str],
    runtime_config_manager: RuntimeConfigManager,
    health_registry: HealthRegistry,
) -> None:
    """Install the auto-gated T5+T7 governed processor after the app lifespan."""
    install_interaction_processor_lifespan(
        app,
        settings,
        db=db,
        tools=tools,
        instructions=instructions,
        runtime_config_manager=runtime_config_manager,
        health_registry=health_registry,
    )


def create_app() -> tuple[FastAPI, AgentOS]:
    settings = Settings()

    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    configure_observability(settings)

    logger.info("Starting AncoraMind — env: %s", settings.app_env)

    # ── Validate required config ──────────────────────
    if not settings.telegram_token:
        logger.error("TELEGRAM_TOKEN is required. Set it in .env or environment.")
        sys.exit(1)
    validate_webhook_secret_settings(settings)
    validate_telegram_admission_settings(settings)
    validate_runtime_config_admin_settings(settings)
    validate_telegram_pairing_admin_settings(settings)
    validate_admin_dashboard_settings(settings)
    runtime_config_manager = create_runtime_config_manager(settings, get_session)
    health_registry = HealthRegistry()
    health_registry.set_component("app", "healthy")

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

    # ── AncoraMind Agent (legacy singleton — transitional until T4/T5 rollout) ──
    ancora_agent = create_ancora_agent(
        model=model,
        db=db,
        tools=tools,
        instructions=instructions,
        tool_call_limit=settings.agent_tool_call_limit,
        retries=0,
    )
    logger.info("AncoraMind agent created")

    # ── AgentOS + Telegram ────────────────────────────
    allowlist = settings.allowed_user_ids
    base_app: FastAPI | None = None
    if (
        settings.telegram_admission_enabled
        or settings.runtime_config_admin_enabled
        or settings.telegram_pairing_admin_enabled
        or settings.admin_dashboard_enabled
    ):
        base_app = FastAPI()
    if settings.telegram_admission_enabled:
        assert base_app is not None
        install_telegram_admission_endpoint(base_app, settings, get_session)
        logger.info("AncoraMind durable Telegram admission enabled at /telegram/webhook")
    if settings.runtime_config_admin_enabled:
        assert base_app is not None
        install_runtime_config_admin_api(base_app, settings, runtime_config_manager)
        logger.info("Runtime config admin API enabled at /admin/runtime-config")
    if settings.telegram_pairing_admin_enabled:
        assert base_app is not None
        install_telegram_pairing_admin_api(base_app, settings, get_session)
        logger.info("Governed Telegram pairing admin API enabled at /admin/telegram-pairing")
    if settings.admin_dashboard_enabled:
        assert base_app is not None
        install_admin_dashboard(
            base_app,
            settings,
            get_session,
            health_registry=health_registry,
            runtime_config_manager=runtime_config_manager,
        )
        logger.info("Operator admin dashboard enabled at /admin/dashboard")

    # The native Agno Telegram interface skips TelegramMediaResolver's size/MIME/
    # path-safety checks and the specs/013/023 governed admission + consent
    # pipeline entirely (BL-39). It only exists as a legacy fallback for when
    # the governed route is off; the two must never both be reachable.
    legacy_interfaces: list[BaseInterface] = (
        []
        if settings.telegram_admission_enabled
        else [
            Telegram(
                agent=ancora_agent,
                reply_to_mentions_only=bool(allowlist),
                reply_to_bot_messages=False,
            )
        ]
    )
    agent_os = AgentOS(
        agents=[ancora_agent],
        db=db,
        interfaces=legacy_interfaces,
        base_app=base_app,
        on_route_conflict="preserve_base_app",
        tracing=False,
        telemetry=False,
        # docs_enabled=False closes /docs, /redoc and /openapi.json
        # entirely outside development (specs/023 T1): AncoraMind never
        # serves that surface in production.
        settings=AgnoAPISettings(docs_enabled=settings.app_env.lower() == "development"),
    )

    app = agent_os.get_app()
    install_health_readiness_endpoint(app, health_registry)
    if settings.agent_os_security_key:
        install_agent_os_rest_guard(app, settings.agent_os_security_key)
        logger.info(
            "AgentOS REST surface gated behind AGENT_OS_SECURITY_KEY "
            "(Telegram/admin/health routes unaffected)"
        )
    logger.info(
        "AgentOS app created — webhook: /telegram/webhook (%s)",
        "AncoraMind admission" if settings.telegram_admission_enabled else "AgentOS",
    )


    # ── Runtime config (T6) ────────────────────────────
    # Install it before workers: outer worker wrappers enter this lifecycle first.
    install_runtime_config_manager_lifespan(
        app,
        settings,
        runtime_config_manager,
        health_registry=health_registry,
    )

    # ── Reminder worker (BL-5) ─────────────────────────
    _register_reminder_worker(app, settings, health_registry)
    _register_interaction_processor(
        app,
        settings,
        db=db,
        tools=tools,
        instructions=instructions,
        runtime_config_manager=runtime_config_manager,
        health_registry=health_registry,
    )
    install_observability_lifespan(app)
    install_health_signals_lifespan(app, settings, health_registry)

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
