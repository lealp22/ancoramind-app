"""FastAPI lifespan infrastructure for AncoraMind background services.

This module belongs to the infrastructure layer: domain workers remain unaware
of FastAPI and AgentOS.  Lifespan wrapping preserves any lifecycle that the
AgentOS application already exposes.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI

from src.agent.governed_agent_factory import GovernedAgentFactory
from src.agent.governed_interaction_runner import GovernedInteractionRunner
from src.agent.health import HealthRegistry, install_health_monitor_lifespan
from src.agent.llm_access import AgnoLLMAccess, LlmUsageRecorder
from src.agent.spend_reader import SessionSpendReader
from src.agent.telegram_admission import validate_telegram_admission_settings
from src.agent.telegram_media import TelegramMediaResolver
from src.config import Settings
from src.domain.emergency_stop.service import EmergencyStopManager
from src.domain.interactions.payloads import TelegramPayloadCipher
from src.domain.interactions.processor import InteractionProcessor
from src.domain.reminders.worker import RemindersWorker
from src.domain.runtime_config.service import RuntimeConfigManager
from src.domain.speech.service import maintain_voice_preparations
from src.notifications.telegram import TelegramNotifier
from src.observability.telemetry import shutdown_observability
from src.repositories.database import get_session

logger = logging.getLogger(__name__)


def install_observability_lifespan(app: FastAPI) -> None:
    """Flush metadata-only telemetry after all application work has stopped.

    Exporter shutdown is best-effort inside ``shutdown_observability``: a
    Collector outage must never turn a healthy process shutdown into a failure.
    """
    previous_lifespan = app.router.lifespan_context

    @asynccontextmanager
    async def observability_lifespan(application: FastAPI) -> AsyncIterator[Any]:
        try:
            async with previous_lifespan(application) as state:
                yield state
        finally:
            try:
                shutdown_observability()
            except Exception:
                logger.warning("Observability shutdown failed; continuing application shutdown")

    app.router.lifespan_context = observability_lifespan


def install_reminder_worker_lifespan(
    app: FastAPI,
    settings: Settings,
    *,
    health_registry: HealthRegistry | None = None,
) -> bool:
    """Install the reminder worker lifecycle wrapper when prerequisites exist.

    The wrapper enters the app's pre-existing lifespan first, starts the
    in-process worker, and always stops it before leaving that original
    lifespan. This avoids replacing AgentOS/Starlette lifecycle behavior.

    Returns:
        True when the worker lifecycle was installed; False when an auto-gate
        deliberately skipped it.
    """
    if not settings.reminder_worker_enabled:
        logger.info("Reminder worker disabled (REMINDER_WORKER_ENABLED=false)")
        return False
    if not settings.ancora_database_url:
        logger.info("Reminder worker skipped — ANCORA_DATABASE_URL not set")
        return False
    if not settings.telegram_token:
        logger.info("Reminder worker skipped — TELEGRAM_TOKEN not set (no notifier)")
        return False

    previous_lifespan = app.router.lifespan_context

    @asynccontextmanager
    async def reminder_worker_lifespan(application: FastAPI) -> AsyncIterator[Any]:
        async with previous_lifespan(application) as state:
            worker = RemindersWorker(
                session_factory=get_session,
                notifier=TelegramNotifier(settings.telegram_token),
                on_cycle=health_registry.record_reminders_delivered
                if health_registry is not None
                else None,
            )
            task = asyncio.create_task(
                worker.run_forever(settings.reminder_poll_interval_seconds),
                name="reminder-worker",
            )
            application.state.reminder_worker_task = task
            logger.info(
                "Reminder worker started (interval=%ss)",
                settings.reminder_poll_interval_seconds,
            )
            try:
                yield state
            finally:
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task
                del application.state.reminder_worker_task
                logger.info("Reminder worker stopped")

    app.router.lifespan_context = reminder_worker_lifespan
    return True


def install_interaction_processor_lifespan(
    app: FastAPI,
    settings: Settings,
    *,
    db: Any,
    tools: list[Any],
    instructions: list[str],
    runtime_config_manager: RuntimeConfigManager,
    health_registry: HealthRegistry | None = None,
    emergency_stop_manager: EmergencyStopManager | None = None,
) -> bool:
    """Install the T5+T7 processor lifecycle only for an explicitly enabled rollout.

    The processor is intentionally gated behind durable admission. It does not
    share in-memory state with the webhook and is always stopped before the
    wrapped lifecycle exits. Every Agent execution is governed: per-run
    factory, immutable snapshot, budget and usage audit (specs/013 T7).
    """
    if not settings.telegram_processor_enabled:
        logger.info("Telegram interaction processor disabled (TELEGRAM_PROCESSOR_ENABLED=false)")
        return False
    if not settings.telegram_admission_enabled:
        logger.info("Telegram interaction processor skipped — durable admission is disabled")
        return False
    validate_telegram_admission_settings(settings)
    if settings.telegram_voice_enabled and not settings.litellm_proxy_enabled:
        raise ValueError("TELEGRAM_VOICE_ENABLED requires the private Gateway")

    previous_lifespan = app.router.lifespan_context
    payload_cipher = TelegramPayloadCipher(
        settings.telegram_payload_encryption_key,
        settings.telegram_payload_key_version,
    )
    llm_access = AgnoLLMAccess(
        settings=settings,
        usage_recorder=LlmUsageRecorder(get_session).record,
        stop_reader=emergency_stop_manager,
    )
    agent_factory = GovernedAgentFactory(
        llm_access=llm_access,
        db=db,
        tools=tools,
        instructions=instructions,
        fingerprint_key=settings.budget_fingerprint_key,
    )
    agent_runner = GovernedInteractionRunner(
        config_manager=runtime_config_manager,
        factory=agent_factory,
        spend_reader=SessionSpendReader(get_session),
        stop_reader=emergency_stop_manager,
    )

    @asynccontextmanager
    async def interaction_processor_lifespan(application: FastAPI) -> AsyncIterator[Any]:
        async with previous_lifespan(application) as state:
            notifier = TelegramNotifier(settings.telegram_token)
            media_resolver = TelegramMediaResolver(settings)
            voice_preparation = None
            if settings.telegram_voice_enabled:
                from src.agent.speech_access import GovernedSpeechAccess
                from src.agent.voice_inspector import FFmpegVoiceInspector
                from src.domain.speech.service import VoicePreparationService

                if runtime_config_manager.snapshot().config.speech is None:
                    raise ValueError(
                        "TELEGRAM_VOICE_ENABLED requires versioned speech configuration"
                    )
                voice_preparation = VoicePreparationService(
                    session_factory=get_session,
                    cipher=payload_cipher,
                    inspector=FFmpegVoiceInspector(),
                    stt=GovernedSpeechAccess(settings, get_session),
                    download=lambda attachment: media_resolver.resolve_voice(
                        attachment, max_bytes=10 * 1024 * 1024
                    ),
                    timeout_seconds=settings.telegram_voice_timeout_seconds,
                )
            processor = InteractionProcessor(
                session_factory=get_session,
                payload_cipher=payload_cipher,
                agent_runner=agent_runner,
                sender=notifier,
                media_resolver=media_resolver,
                global_concurrency=settings.telegram_processor_global_concurrency,
                governed_consent=settings.governed_consent_enabled,
                voice_enabled=settings.telegram_voice_enabled,
                voice_preparation=voice_preparation,
                voice_maintenance=lambda: maintain_voice_preparations(get_session),
                on_cycle=(lambda _: health_registry.heartbeat("interaction_processor"))
                if health_registry is not None
                else None,
                on_interaction_completed=health_registry.record_interaction_processed
                if health_registry is not None
                else None,
            )
            ambiguous = await processor.recover_once()
            if ambiguous:
                logger.warning(
                    "Telegram processor marked %d in-flight interaction(s) failed_ambiguous",
                    ambiguous,
                )
            task = asyncio.create_task(
                processor.run_forever(settings.telegram_processor_poll_interval_seconds),
                name="telegram-interaction-processor",
            )
            application.state.telegram_interaction_processor_task = task
            logger.info(
                "Telegram interaction processor started (interval=%ss, concurrency=%s)",
                settings.telegram_processor_poll_interval_seconds,
                settings.telegram_processor_global_concurrency,
            )
            try:
                yield state
            finally:
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task
                del application.state.telegram_interaction_processor_task
                await notifier.close()
                await media_resolver.close()
                logger.info("Telegram interaction processor stopped")

    app.router.lifespan_context = interaction_processor_lifespan
    return True


def install_runtime_config_manager_lifespan(
    app: FastAPI,
    settings: Settings,
    manager: RuntimeConfigManager,
    health_registry: HealthRegistry | None = None,
) -> bool:
    """Initialize the T6 in-memory snapshot before accepting application traffic."""
    previous_lifespan = app.router.lifespan_context

    @asynccontextmanager
    async def runtime_config_lifespan(application: FastAPI) -> AsyncIterator[Any]:
        async with previous_lifespan(application) as state:
            await manager.initialize()
            application.state.runtime_config_manager = manager
            if health_registry is not None:
                health_registry.set_runtime_config_revision(
                    manager.snapshot().revision,
                    database_available=manager.database_available,
                )
            logger.info(
                "Runtime config initialized (source=%s, revision=%s, database_available=%s)",
                manager.snapshot().source,
                manager.snapshot().revision,
                manager.database_available,
            )
            try:
                yield state
            finally:
                del application.state.runtime_config_manager

    app.router.lifespan_context = runtime_config_lifespan
    return True


def install_health_signals_lifespan(
    app: FastAPI,
    settings: Settings,
    registry: HealthRegistry,
) -> None:
    """Install the final, fail-open health monitor around all runtime lifespans."""
    install_health_monitor_lifespan(app, settings, session_factory=get_session, registry=registry)
