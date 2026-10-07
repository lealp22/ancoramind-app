"""Contract tests for fail-fast repository INSERT ... RETURNING guards."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, date, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.calendar.models import CalendarEventCreate
from src.domain.documents.models import AIExtractionCreate, DocumentCreate
from src.domain.notes.models import NoteCreate
from src.domain.reminders.models import ReminderCreate
from src.domain.vehicles.models import VehicleCreate, VehicleMaintenanceCreate
from src.repositories.actions import ActionProposalsRepository
from src.repositories.calendar import CalendarRepository
from src.repositories.documents import DocumentsRepository
from src.repositories.maintenance import MaintenanceRepository
from src.repositories.notes import NotesRepository
from src.repositories.reminders import RemindersRepository
from src.repositories.vehicles import VehiclesRepository

RepositoryCall = Callable[[AsyncSession], Awaitable[object]]


def _session_without_returning_row() -> AsyncSession:
    session = AsyncMock(spec=AsyncSession)
    result = MagicMock()
    result.fetchone.return_value = None
    session.execute.return_value = result
    return session


@pytest.mark.parametrize(
    ("operation", "expected_message"),
    [
        (
            lambda session: NotesRepository(session).create("user-1", NoteCreate(content="Nota")),
            "Note insert did not return a row",
        ),
        (
            lambda session: VehiclesRepository(session).create(
                "user-1", VehicleCreate(make="Ford", model="Focus")
            ),
            "Vehicle insert did not return a row",
        ),
        (
            lambda session: MaintenanceRepository(session).create(
                "user-1",
                VehicleMaintenanceCreate(
                    vehicle_id=uuid4(), date=date(2026, 9, 27), description="Cambio de aceite"
                ),
            ),
            "Vehicle maintenance insert did not return a row",
        ),
        (
            lambda session: DocumentsRepository(session).create(
                "user-1",
                DocumentCreate(
                    storage_key="synthetic/document.pdf",
                    original_filename="document.pdf",
                    mime_type="application/pdf",
                    size_bytes=1,
                    content_hash="f" * 64,
                ),
            ),
            "Document insert did not return a row",
        ),
        (
            lambda session: DocumentsRepository(session).create_extraction(
                AIExtractionCreate(
                    document_id=uuid4(),
                    provider="synthetic",
                    model="synthetic-model",
                    prompt_version="test",
                    schema_version="v1",
                    extraction={},
                )
            ),
            "AI extraction insert did not return a row",
        ),
        (
            lambda session: RemindersRepository(session).create(
                "user-1",
                ReminderCreate(title="ITV", trigger_at=datetime(2026, 9, 28, tzinfo=UTC)),
            ),
            "Reminder insert did not return a row",
        ),
        (
            lambda session: CalendarRepository(session).create(
                "user-1",
                CalendarEventCreate(
                    title="Cita", start_at=datetime(2026, 9, 28, tzinfo=UTC)
                ),
                provider_event_id=None,
            ),
            "Calendar event insert did not return a row",
        ),
        (
            lambda session: ActionProposalsRepository(session).create(
                "user-1", "create_reminder", {"title": "ITV"}
            ),
            "Action proposal insert did not return a row",
        ),
    ],
)
async def test_insert_returning_without_row_fails_before_commit(
    operation: RepositoryCall,
    expected_message: str,
) -> None:
    """A driver anomaly must not commit or fabricate a canonical record."""

    session = _session_without_returning_row()

    with pytest.raises(RuntimeError, match=expected_message):
        await operation(session)

    session.commit.assert_not_awaited()
