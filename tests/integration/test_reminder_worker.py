"""Integration tests for the reminder worker against real PostgreSQL (specs/010)."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from src.domain.reminders.models import ReminderCreate
from src.domain.reminders.worker import RemindersWorker
from src.repositories.reminders import RemindersRepository

pytestmark = pytest.mark.integration


async def test_worker_fires_due_reminders_only(session, user_a):
    repo = RemindersRepository(session)
    due = await repo.create(
        user_a,
        ReminderCreate(
            title="Vencida",
            trigger_at=datetime.now(tz=UTC) - timedelta(minutes=5),
        ),
    )
    future = await repo.create(
        user_a,
        ReminderCreate(
            title="Futura",
            trigger_at=datetime.now(tz=UTC) + timedelta(days=1),
        ),
    )

    notifier = AsyncMock()
    notifier.send_reminder.return_value = True

    async def session_factory():
        return session

    worker = RemindersWorker(session_factory=session_factory, notifier=notifier)
    fired = await worker.run_once()

    assert fired == 1
    notifier.send_reminder.assert_awaited_once()
    notified = notifier.send_reminder.await_args.args[0]
    assert notified.id == due.id

    # Real DB state: the due one fired, the future one is still pending
    fired_rows = await repo.list_by_user(user_a, status="fired")
    assert [r.title for r in fired_rows] == ["Vencida"]
    pending_rows = await repo.list_by_user(user_a, status="pending")
    assert [r.id for r in pending_rows] == [future.id]

    # A second cycle does not re-notify: mark_fired is idempotent on status
    assert await worker.run_once() == 0
    notifier.send_reminder.assert_awaited_once()
