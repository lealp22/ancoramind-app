"""Reminder domain service."""

from datetime import datetime
from uuid import UUID

from src.domain.preferences.timezone import resolve_user_timezone, to_utc
from src.domain.reminders.models import Reminder, ReminderCreate
from src.repositories.reminders import RemindersRepository
from src.security.user_context import UserContext


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
    ) -> Reminder:
        """Create a reminder (WRITE — caller handles confirmation).

        ``trigger_at`` may be naive (interpreted in the user's resolved
        timezone — specs/023 T5.2) or timezone-aware (used as-is); either
        way it is normalized to UTC before persisting.

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
        )
        return await self._repo.create(user_context.user_id, data)

    async def list_reminders(
        self, user_context: UserContext, status: str | None = None
    ) -> list[Reminder]:
        """List reminders (pending by default)."""
        return await self._repo.list_by_user(user_context.user_id, status)
