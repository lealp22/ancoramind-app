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

from src.config import Settings
from src.domain.reminders.worker import RemindersWorker
from src.notifications.telegram import TelegramNotifier
from src.repositories.database import get_session

logger = logging.getLogger(__name__)


def install_reminder_worker_lifespan(app: FastAPI, settings: Settings) -> bool:
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
