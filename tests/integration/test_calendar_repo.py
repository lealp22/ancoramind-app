"""Integration tests for CalendarRepository against real PostgreSQL (specs/009)."""

from datetime import UTC, datetime

import pytest

from src.domain.calendar.models import CalendarEventCreate
from src.repositories.calendar import CalendarRepository

pytestmark = pytest.mark.integration


async def test_create_and_list_range_inclusive(session, user_a, user_b):
    repo = CalendarRepository(session)

    await repo.create(
        user_a,
        CalendarEventCreate(
            title="Dentista",
            start_at=datetime(2026, 9, 10, 10, 0, tzinfo=UTC),
            end_at=datetime(2026, 9, 10, 11, 0, tzinfo=UTC),
            location="Clínica",
        ),
        provider_event_id="noop:1",
    )
    await repo.create(
        user_a,
        CalendarEventCreate(title="Inicio", start_at=datetime(2026, 9, 8, tzinfo=UTC)),
        provider_event_id=None,
    )
    await repo.create(
        user_a,
        CalendarEventCreate(title="Fin", start_at=datetime(2026, 9, 12, tzinfo=UTC)),
        provider_event_id=None,
    )
    await repo.create(
        user_a,
        CalendarEventCreate(title="Fuera", start_at=datetime(2026, 9, 13, tzinfo=UTC)),
        provider_event_id=None,
    )

    events = await repo.list_range(
        user_a,
        datetime(2026, 9, 8, tzinfo=UTC),
        datetime(2026, 9, 12, tzinfo=UTC),
    )
    # Boundaries are inclusive; results ordered by start_at
    assert [e.title for e in events] == ["Inicio", "Dentista", "Fin"]
    assert all(e.start_at.tzinfo is not None for e in events)

    # User scoping
    assert (
        await repo.list_range(
            user_b,
            datetime(2026, 9, 8, tzinfo=UTC),
            datetime(2026, 9, 12, tzinfo=UTC),
        )
        == []
    )
