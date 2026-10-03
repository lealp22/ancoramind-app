"""Calendar repository — parameterized SQL."""

from datetime import UTC, datetime

from sqlalchemy import Row, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.calendar.models import CalendarEvent, CalendarEventCreate
from src.domain.shared.recurrence import rule_to_jsonb_param


class CalendarRepository:
    """Repository for calendar events in ancora schema."""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def create(
        self, user_id: str, data: CalendarEventCreate, provider_event_id: str | None
    ) -> CalendarEvent:
        now = datetime.now(tz=UTC)
        stmt = text("""
            INSERT INTO ancora.calendar_events
                (user_id,title,description,location,start_at,end_at,provider_event_id,
                 source_document_id,created_at,recurrence_rule)
            VALUES (:uid,:title,:desc,:loc,:start,:end,:peid,:src,:now,CAST(:rec AS jsonb))
            RETURNING *
        """)
        r = await self._session.execute(stmt, {
            "uid": user_id, "title": data.title, "desc": data.description,
            "loc": data.location, "start": data.start_at, "end": data.end_at,
            "peid": provider_event_id, "src": data.source_document_id, "now": now,
            "rec": rule_to_jsonb_param(data.recurrence_rule),
        })
        row = r.fetchone()
        if row is None:
            raise RuntimeError("Calendar event insert did not return a row")
        await self._session.commit()
        return _row_to_event(row)

    async def list_range(
        self, user_id: str, start: datetime, end: datetime
    ) -> list[CalendarEvent]:
        """Rows in [start, end], plus every recurring anchor regardless of its
        own start_at — the service expands recurrence and applies the final
        range filter, since a recurring anchor's original start_at may be in
        the past (e.g. a birthday created last year) yet still produce an
        occurrence inside the requested range.
        """
        stmt = text("""
            SELECT * FROM ancora.calendar_events
            WHERE user_id=:uid
              AND ((start_at >= :start AND start_at <= :end) OR recurrence_rule IS NOT NULL)
            ORDER BY start_at
        """)
        r = await self._session.execute(stmt, {"uid": user_id, "start": start, "end": end})
        return [_row_to_event(row) for row in r.fetchall()]


def _row_to_event(row: Row[tuple[object, ...]]) -> CalendarEvent:
    return CalendarEvent(
        id=row.id, user_id=row.user_id, title=row.title, description=row.description,
        location=row.location, start_at=row.start_at, end_at=row.end_at,
        provider_event_id=row.provider_event_id, source_document_id=row.source_document_id,
        created_at=row.created_at, recurrence_rule=row.recurrence_rule,
    )
