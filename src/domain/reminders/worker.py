"""Reminder background worker — fires due reminders (BL-5, specs/010).

Domain orchestration: scans pending reminders whose trigger_at has passed,
notifies via an injected notifier (Protocol) and marks them fired only when
delivery succeeded. No Agno/Telegram imports here (ADR-001, ADR-003).
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.reminders.models import Reminder
from src.domain.shared.recurrence import next_occurrence
from src.repositories.reminders import RemindersRepository

logger = logging.getLogger(__name__)

RETENTION_DAYS = 90
"""Fired reminders older than this are purged each cycle (specs/024)."""


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
                    delivered_at = datetime.now(tz=UTC)
                    logger.info(
                        "Reminder delivered (reminder_id=%s, trigger_at_utc=%s, "
                        "delivered_at_utc=%s, delay_seconds=%.3f)",
                        reminder.id,
                        reminder.trigger_at.isoformat(),
                        delivered_at.isoformat(),
                        max(0.0, (delivered_at - reminder.trigger_at).total_seconds()),
                    )
                    if reminder.recurrence_rule is not None:
                        await self._advance_recurrence(repo, reminder)
                else:
                    logger.warning(
                        "Reminder delivery failed; left pending for retry: "
                        "%s (user %s)",
                        reminder.id, reminder.user_id,
                    )
            deleted = await repo.delete_old_fired(
                before=datetime.now(tz=UTC) - timedelta(days=RETENTION_DAYS)
            )
            if deleted:
                logger.info(
                    "Retention: deleted %d fired reminder(s) older than %d days",
                    deleted, RETENTION_DAYS,
                )
        finally:
            await session.close()
        return fired

    @staticmethod
    async def _advance_recurrence(repo: RemindersRepository, fired: Reminder) -> None:
        """Insert the next pending occurrence of a just-fired recurring reminder.

        Monthly/yearly clamping is anchored to the chain's root (this row
        itself if it has no parent, otherwise the parent row) so the day of
        month never drifts across occurrences (see
        src.domain.shared.recurrence.next_occurrence).
        """
        anchor = fired
        if fired.recurrence_parent_id is not None:
            root = await repo.get_by_id(fired.user_id, fired.recurrence_parent_id)
            if root is not None:
                anchor = root
        assert fired.recurrence_rule is not None  # guarded by caller
        next_trigger = next_occurrence(
            fired.recurrence_rule, anchor=anchor.trigger_at, after=fired.trigger_at
        )
        if next_trigger is None:
            return
        await repo.create_next_occurrence(fired, next_trigger)
        logger.info(
            "Recurring reminder advanced: %s -> next occurrence at %s",
            fired.id, next_trigger.isoformat(),
        )

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
