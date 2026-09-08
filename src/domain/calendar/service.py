"""Calendar domain service — decoupled from external calendar SDK."""

from datetime import datetime
from uuid import UUID

from src.domain.calendar.models import CalendarEvent, CalendarEventCreate
from src.domain.calendar.provider import CalendarProvider
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
        """Create an event (EXTERNAL_ACTION — caller handles confirmation)."""
        data = CalendarEventCreate(
            title=title, start_at=start_at, end_at=end_at,
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
