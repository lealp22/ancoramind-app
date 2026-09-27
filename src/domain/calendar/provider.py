"""Calendar provider abstraction — decouples domain from external calendar SDK."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from src.domain.calendar.models import CalendarEventCreate


class CalendarProvider(Protocol):
    """Protocol for external calendar providers (Google, Outlook, etc.).

    The domain depends on this protocol, never on a concrete SDK.
    """

    async def create_event(
        self, user_external_id: str, data: CalendarEventCreate
    ) -> str:
        """Create an event in the external calendar.

        Returns:
            Provider-specific event ID.
        """
        ...

    async def list_events(
        self, user_external_id: str, start: datetime, end: datetime
    ) -> list[dict[str, object]]:
        """List events in a date range from the external calendar."""
        ...


class NoopCalendarProvider:
    """POC placeholder — doesn't call any external service.

    Stores events only in AncoraMind's canonical PostgreSQL (via service),
    and returns a synthetic provider ID. This satisfies the abstraction
    boundary while no real calendar provider is configured.
    """

    async def create_event(
        self, user_external_id: str, data: CalendarEventCreate
    ) -> str:
        return f"noop:{user_external_id}:{data.start_at.timestamp():.0f}"

    async def list_events(
        self, user_external_id: str, start: datetime, end: datetime
    ) -> list[dict[str, object]]:
        return []
