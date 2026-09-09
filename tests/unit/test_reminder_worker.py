"""Unit tests for the reminder background worker (BL-5, specs/010)."""

import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

import src.domain.reminders.worker as worker_module
from src.domain.reminders.models import Reminder
from src.domain.reminders.worker import RemindersWorker
from src.repositories.reminders import RemindersRepository


def _reminder(title: str = "ITV", minutes_ago: float = 0) -> Reminder:
    return Reminder(
        id=uuid4(),
        user_id="452022640",
        title=title,
        description=None,
        trigger_at=datetime.now(tz=UTC) - timedelta(minutes=minutes_ago),
        status="pending",
        source_document_id=None,
        source_action_id=None,
        created_at=datetime.now(tz=UTC),
    )


@pytest.fixture
def session() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def repo(session, monkeypatch) -> AsyncMock:
    """Replace the repository class the worker builds with an AsyncMock.

    The worker constructs RemindersRepository from the session factory; the
    monkeypatch is scoped to the worker module and auto-reverts per test.
    """
    repo_mock = AsyncMock(spec=RemindersRepository)
    monkeypatch.setattr(worker_module, "RemindersRepository", lambda _: repo_mock)
    return repo_mock


def _make_worker(session: AsyncMock, notifier: AsyncMock) -> RemindersWorker:
    async def session_factory():
        return session

    return RemindersWorker(session_factory=session_factory, notifier=notifier)


async def test_run_once_fires_all_due_reminders(session, repo):
    r1, r2 = _reminder("ITV"), _reminder("Renovar seguro")
    notifier = AsyncMock()
    notifier.send_reminder.return_value = True
    repo.list_due.return_value = [r1, r2]

    worker = _make_worker(session, notifier)
    fired = await worker.run_once()

    assert fired == 2
    repo.mark_fired.assert_any_await(r1.id, r1.user_id)
    repo.mark_fired.assert_any_await(r2.id, r2.user_id)
    assert notifier.send_reminder.await_count == 2
    session.close.assert_awaited_once()


async def test_run_once_leaves_pending_when_delivery_fails(session, repo):
    reminder = _reminder()
    notifier = AsyncMock()
    notifier.send_reminder.return_value = False
    repo.list_due.return_value = [reminder]

    worker = _make_worker(session, notifier)
    fired = await worker.run_once()

    assert fired == 0
    repo.mark_fired.assert_not_awaited()
    session.close.assert_awaited_once()


async def test_run_once_continues_after_notifier_error(session, repo):
    bad, good = _reminder("falla"), _reminder("funciona")
    notifier = AsyncMock()
    notifier.send_reminder.side_effect = [RuntimeError("boom"), True]
    repo.list_due.return_value = [bad, good]

    worker = _make_worker(session, notifier)
    fired = await worker.run_once()

    assert fired == 1
    repo.mark_fired.assert_awaited_once_with(good.id, good.user_id)
    assert notifier.send_reminder.await_count == 2
    session.close.assert_awaited_once()


async def test_run_once_without_due_reminders_does_nothing(session, repo):
    notifier = AsyncMock()
    repo.list_due.return_value = []

    worker = _make_worker(session, notifier)
    fired = await worker.run_once()

    assert fired == 0
    notifier.send_reminder.assert_not_awaited()
    repo.mark_fired.assert_not_awaited()
    session.close.assert_awaited_once()


async def test_run_forever_survives_errors_and_cancels_cleanly(monkeypatch):
    worker = RemindersWorker(session_factory=AsyncMock(), notifier=AsyncMock())
    calls = {"count": 0}

    async def fake_run_once():
        calls["count"] += 1
        if calls["count"] == 1:
            raise ValueError("cycle failure must not kill the loop")
        return 0

    monkeypatch.setattr(worker, "run_once", fake_run_once)

    task = asyncio.create_task(worker.run_forever(interval_seconds=0.01))
    await asyncio.sleep(0.05)  # several cycles, including some after the error
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task

    assert calls["count"] >= 2

