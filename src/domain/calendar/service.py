"""Calendar domain service — decoupled from external calendar SDK."""

from datetime import datetime
from uuid import UUID

from src.domain.calendar.models import CalendarEvent, CalendarEventCreate
from src.domain.calendar.provider import CalendarProvider
from src.domain.preferences.timezone import resolve_user_timezone, to_utc
from src.domain.shared.recurrence import RecurrenceRule, occurrences_in_range
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
        recurrence_rule: RecurrenceRule | None = None,
    ) -> CalendarEvent:
        """Create an event (EXTERNAL_ACTION — caller handles confirmation).

        ``start_at``/``end_at`` may be naive (interpreted in the user's
        resolved timezone — specs/023 T5.2) or timezone-aware (used as-is);
        either way they are normalized to UTC before persisting. A
        ``recurrence_rule`` is stored as-is on this single row — recurring
        occurrences are never materialized, only expanded virtually by
        ``check_calendar`` (specs/024).

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
            recurrence_rule=recurrence_rule,
        )
        # Call external provider (or Noop placeholder)
        provider_id = await self._provider.create_event(user_context.user_id, data)
        return await self._repo.create(user_context.user_id, data, provider_id)

    async def check_calendar(
        self, user_context: UserContext, start: datetime, end: datetime
    ) -> list[CalendarEvent]:
        """List events in a date range, expanding recurring anchors virtually.

        A row with no ``recurrence_rule`` is included only if its own
        ``start_at`` falls in range (as before). A recurring row is never
        returned as-is: it is expanded into zero or more virtual occurrences
        within ``[start, end]`` (same ``id``, adjusted ``start_at``/``end_at``
        preserving the original duration) — nothing is persisted per
        occurrence (specs/024).
        """
        rows = await self._repo.list_range(user_context.user_id, start, end)
        expanded: list[CalendarEvent] = []
        for row in rows:
            if row.recurrence_rule is None:
                if start <= row.start_at <= end:
                    expanded.append(row)
                continue
            duration = (row.end_at - row.start_at) if row.end_at else None
            for occ_start in occurrences_in_range(row.recurrence_rule, row.start_at, start, end):
                expanded.append(row.model_copy(update={
                    "start_at": occ_start,
                    "end_at": occ_start + duration if duration else None,
                }))
        expanded.sort(key=lambda e: e.start_at)
        return expanded
