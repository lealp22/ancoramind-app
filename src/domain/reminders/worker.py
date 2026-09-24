"""Reminder background worker — fires due reminders (BL-5, specs/010).

Domain orchestration: scans pending reminders whose trigger_at has passed,
notifies via an injected notifier (Protocol) and marks them fired only when
delivery succeeded. No Agno/Telegram imports here (ADR-001, ADR-003).
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.reminders.models import Reminder
from src.repositories.reminders import RemindersRepository

logger = logging.getLogger(__name__)


class ReminderNotifier(Protocol):
    """Delivery channel for fired reminders (e.g. TelegramNotifier)."""

    async def send_reminder(self, reminder: Reminder) -> bool:
        """Deliver the reminder. Returns True on confirmed delivery."""
        ...


class RemindersWorker:
    """Periodic worker that fires due reminders (BL-5).

    Firing is the deferred execution of an already user-confirmed action
    (propose/execute), so pending→fired needs no new ActionProposal
    (ADR-003 governance note).
    """

    def __init__(
        self,
        session_factory: Callable[[], Awaitable[AsyncSession]],
        notifier: ReminderNotifier,
        on_cycle: Callable[[int], None] | None = None,
    ):
        self._session_factory = session_factory
        self._notifier = notifier
        self._on_cycle = on_cycle

    async def run_once(self) -> int:
        """Fire all currently due reminders; returns how many were fired."""
        session = await self._session_factory()
        repo = RemindersRepository(session)
        fired = 0
        try:
            due = await repo.list_due(datetime.now(tz=UTC))
            for reminder in due:
                try:
                    delivered = await self._notifier.send_reminder(reminder)
                except Exception:
                    logger.exception(
                        "Reminder delivery raised for %s (user %s); left pending",
                        reminder.id,
                        reminder.user_id,
                    )
                    continue
                if delivered:
                    await repo.mark_fired(reminder.id, reminder.user_id)
                    fired += 1
                    logger.info(
                        "Reminder fired: %s (user %s, due %s)",
                        reminder.id, reminder.user_id, reminder.trigger_at.isoformat(),
                    )
                else:
                    logger.warning(
                        "Reminder delivery failed; left pending for retry: "
                        "%s (user %s)",
                        reminder.id, reminder.user_id,
                    )
        finally:
            await session.close()
        return fired

    async def run_forever(self, interval_seconds: float) -> None:
        """Poll forever; per-cycle errors are logged, never kill the loop."""
        while True:
            try:
                fired = await self.run_once()
                if self._on_cycle is not None:
                    self._on_cycle(fired)
                if fired:
                    logger.info("Reminder worker cycle fired %d reminder(s)", fired)
            except asyncio.CancelledError:
                logger.info("Reminder worker cancelled")
                raise
            except Exception:
                logger.exception("Reminder worker cycle failed; retrying next cycle")
            await asyncio.sleep(interval_seconds)
