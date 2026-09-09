"""Integration tests for RemindersRepository against real PostgreSQL (specs/009)."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from src.domain.reminders.models import ReminderCreate
from src.repositories.actions import ActionProposalsRepository
from src.repositories.reminders import RemindersRepository

pytestmark = pytest.mark.integration


async def test_create_and_list_with_status_filter(session, user_a, user_b):
    actions = ActionProposalsRepository(session)
    repo = RemindersRepository(session)

    proposal = await actions.create(user_a, "create_reminder", {"title": "ITV"})
    reminder = await repo.create(
        user_a,
        ReminderCreate(
            title="ITV",
            description="Pedir cita",
            trigger_at=datetime(2026, 10, 1, 9, 0, tzinfo=UTC),
            source_action_id=UUID(proposal["id"]),
        ),
    )
    assert reminder.status == "pending"  # DB default
    assert reminder.trigger_at.tzinfo is not None

    await repo.create(
        user_a,
        ReminderCreate(title="Otro", trigger_at=datetime(2026, 11, 1, tzinfo=UTC)),
    )

    assert len(await repo.list_by_user(user_a)) == 2
    assert len(await repo.list_by_user(user_a, status="pending")) == 2
    assert await repo.list_by_user(user_b) == []
    assert await repo.list_by_user(user_b, status="pending") == []


async def test_fk_requires_existing_source_action(session, user_a):
    repo = RemindersRepository(session)

    with pytest.raises(IntegrityError):
        await repo.create(
            user_a,
            ReminderCreate(
                title="huérfano",
                trigger_at=datetime(2026, 1, 1, tzinfo=UTC),
                source_action_id=uuid4(),
            ),
        )
    await session.rollback()
