"""Reminder domain service."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

from pydantic import BaseModel, Field

from src.domain.preferences.timezone import resolve_user_timezone, to_utc
from src.domain.reminders.models import Reminder, ReminderCreate
from src.domain.shared.recurrence import RecurrenceRule
from src.repositories.reminders import RemindersRepository
from src.security.user_context import UserContext


class SnoozeRequest(BaseModel):
    """Validated bounds for a reminder snooze (specs/024)."""

    minutes: int = Field(ge=5, le=10_080)


class ReminderService:
    """Service for managing personal reminders."""

    def __init__(self, repository: RemindersRepository):
        self._repo = repository

    async def create_reminder(
        self,
        user_context: UserContext,
        title: str,
        trigger_at: datetime,
        description: str | None = None,
        source_document_id: UUID | None = None,
        source_action_id: UUID | None = None,
        recurrence_rule: RecurrenceRule | None = None,
    ) -> Reminder:
        """Create a reminder (WRITE — caller handles confirmation).

        ``trigger_at`` may be naive (interpreted in the user's resolved
        timezone — specs/023 T5.2) or timezone-aware (used as-is); either
        way it is normalized to UTC before persisting. A ``recurrence_rule``
        is stored on this row and used by the worker to advance to the next
        occurrence once this one fires (specs/024).

        Raises:
            AmbiguousOrNonExistentTimeError: if a naive ``trigger_at`` falls
                in a DST fold/gap in the resolved timezone.
        """
        tz = resolve_user_timezone(user_context)
        data = ReminderCreate(
            title=title,
            trigger_at=to_utc(trigger_at, tz),
            description=description,
            source_document_id=source_document_id,
            source_action_id=source_action_id,
            recurrence_rule=recurrence_rule,
        )
        return await self._repo.create(user_context.user_id, data)

    async def list_reminders(
        self, user_context: UserContext, status: str | None = None
    ) -> list[Reminder]:
        """List reminders (pending by default)."""
        return await self._repo.list_by_user(user_context.user_id, status)

    async def snooze_reminder(
        self, user_context: UserContext, original_id: UUID, minutes: int, proposal_id: UUID
    ) -> Reminder | None:
        """Postpone a reminder: create a one-off copy N minutes from now.

        Independent of any recurrence the original has — the snoozed copy
        never recurs itself (specs/024). Not restricted to already-``fired``
        reminders, keeping the flow simple (list_reminders -> id -> snooze).
        Returns ``None`` if ``original_id`` doesn't exist or isn't owned by
        this user — the tool layer turns that into a user-facing message.
        """
        SnoozeRequest(minutes=minutes)  # raises ValueError if out of [5, 10_080]
        original = await self._repo.get_by_id(user_context.user_id, original_id)
        if original is None:
            return None
        trigger_at = datetime.now(tz=UTC) + timedelta(minutes=minutes)
        return await self._repo.create_snoozed(original, trigger_at, proposal_id)
