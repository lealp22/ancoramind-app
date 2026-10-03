"""Calendar domain service — decoupled from external calendar SDK."""

from datetime import datetime
from uuid import UUID

from src.domain.calendar.models import CalendarEvent, CalendarEventCreate
from src.domain.calendar.provider import CalendarProvider
from src.domain.preferences.timezone import resolve_user_timezone, to_utc
from src.repositories.calendar import CalendarRepository
from src.security.user_context import UserContext


class CalendarService:
    """Service for managing calendar events via a provider abstraction."""

    def __init__(self, repository: CalendarRepository, provider: CalendarProvider):
        self._repo = repository
        self._provider = provider

    async def create_event(
        self,
        user_context: UserContext,
        title: str,
        start_at: datetime,
        end_at: datetime | None = None,
        description: str | None = None,
        location: str | None = None,
        source_document_id: UUID | None = None,
    ) -> CalendarEvent:
        """Create an event (EXTERNAL_ACTION — caller handles confirmation).

        ``start_at``/``end_at`` may be naive (interpreted in the user's
        resolved timezone — specs/023 T5.2) or timezone-aware (used as-is);
        either way they are normalized to UTC before persisting.

        Raises:
            AmbiguousOrNonExistentTimeError: if a naive value falls in a
                DST fold/gap in the resolved timezone.
        """
        tz = resolve_user_timezone(user_context)
        data = CalendarEventCreate(
            title=title,
            start_at=to_utc(start_at, tz),
            end_at=to_utc(end_at, tz) if end_at is not None else None,
            description=description, location=location,
            source_document_id=source_document_id,
        )
        # Call external provider (or Noop placeholder)
        provider_id = await self._provider.create_event(user_context.user_id, data)
        return await self._repo.create(user_context.user_id, data, provider_id)

    async def check_calendar(
        self, user_context: UserContext, start: datetime, end: datetime
    ) -> list[CalendarEvent]:
        """List events in a date range (canonical store)."""
        return await self._repo.list_range(user_context.user_id, start, end)
