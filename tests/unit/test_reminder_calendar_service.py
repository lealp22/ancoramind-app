"""Unit tests for Reminder and Calendar services (mocked repos)."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.domain.calendar.provider import NoopCalendarProvider
from src.domain.calendar.service import CalendarService
from src.domain.reminders.models import Reminder
from src.domain.reminders.service import ReminderService
from src.security.user_context import UserContext


@pytest.fixture
def user_ctx():
    return UserContext(user_id="test-user")


class TestReminderService:
    async def test_create_reminder(self, user_ctx):
        repo = AsyncMock()
        expected = Reminder(id=uuid4(), user_id="test-user", title="t",
                            description=None, trigger_at=datetime(2026, 8, 28, tzinfo=timezone.utc),
                            status="pending", source_document_id=None, source_action_id=None,
                            created_at=datetime(2026, 8, 24, tzinfo=timezone.utc))
        repo.create.return_value = expected
        service = ReminderService(repo)

        result = await service.create_reminder(
            user_ctx, "t", datetime(2026, 8, 28, tzinfo=timezone.utc),
        )
        assert result == expected
        args = repo.create.call_args[0]
        assert args[0] == "test-user"
        assert args[1].title == "t"

    async def test_list_reminders(self, user_ctx):
        repo = AsyncMock()
        repo.list_by_user.return_value = []
        service = ReminderService(repo)
        result = await service.list_reminders(user_ctx, status="pending")
        assert result == []
        repo.list_by_user.assert_awaited_once_with("test-user", "pending")


class TestCalendarService:
    async def test_create_event_calls_provider(self, user_ctx):
        repo = AsyncMock()
        provider = AsyncMock(spec=NoopCalendarProvider)
        provider.create_event.return_value = "noop:abc"
        repo.create.return_value = None
        service = CalendarService(repo, provider)

        await service.create_event(user_ctx, "Dentista", datetime(2026, 8, 28, 17, 30, tzinfo=timezone.utc))
        provider.create_event.assert_awaited_once()
        repo.create.assert_awaited_once()

    async def test_check_calendar(self, user_ctx):
        repo = AsyncMock()
        repo.list_range.return_value = []
        provider = NoopCalendarProvider()
        service = CalendarService(repo, provider)
        start = datetime(2026, 8, 24, tzinfo=timezone.utc)
        end = datetime(2026, 8, 30, tzinfo=timezone.utc)
        result = await service.check_calendar(user_ctx, start, end)
        assert result == []
        repo.list_range.assert_awaited_once_with("test-user", start, end)