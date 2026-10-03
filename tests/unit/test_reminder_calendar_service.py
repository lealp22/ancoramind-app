"""Unit tests for Reminder and Calendar services (mocked repos)."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.domain.calendar.provider import NoopCalendarProvider
from src.domain.calendar.service import CalendarService
from src.domain.preferences.timezone import AmbiguousOrNonExistentTimeError
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
                            description=None, trigger_at=datetime(2026, 8, 28, tzinfo=UTC),
                            status="pending", source_document_id=None, source_action_id=None,
                            created_at=datetime(2026, 8, 24, tzinfo=UTC))
        repo.create.return_value = expected
        service = ReminderService(repo)

        result = await service.create_reminder(
            user_ctx, "t", datetime(2026, 8, 28, tzinfo=UTC),
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

    async def test_create_reminder_normalizes_naive_summer_input_to_utc(self, user_ctx):
        """specs/023 T5.2/T5.5: 17:00 naive, Europe/Madrid summer (UTC+2) -> 15:00Z."""
        repo = AsyncMock()
        service = ReminderService(repo)

        await service.create_reminder(user_ctx, "t", datetime(2026, 8, 28, 17, 0))

        data = repo.create.call_args[0][1]
        assert data.trigger_at == datetime(2026, 8, 28, 15, 0, tzinfo=UTC)

    async def test_create_reminder_normalizes_naive_winter_input_to_utc(self, user_ctx):
        """17:00 naive, Europe/Madrid winter (UTC+1) -> 16:00Z."""
        repo = AsyncMock()
        service = ReminderService(repo)

        await service.create_reminder(user_ctx, "t", datetime(2026, 1, 15, 17, 0))

        data = repo.create.call_args[0][1]
        assert data.trigger_at == datetime(2026, 1, 15, 16, 0, tzinfo=UTC)

    async def test_create_reminder_rejects_ambiguous_naive_input(self, user_ctx):
        """2026-10-25 02:30 occurs twice in Europe/Madrid (DST fall-back)."""
        repo = AsyncMock()
        service = ReminderService(repo)

        with pytest.raises(AmbiguousOrNonExistentTimeError):
            await service.create_reminder(user_ctx, "t", datetime(2026, 10, 25, 2, 30))
        repo.create.assert_not_awaited()


class TestCalendarService:
    async def test_create_event_calls_provider(self, user_ctx):
        repo = AsyncMock()
        provider = AsyncMock(spec=NoopCalendarProvider)
        provider.create_event.return_value = "noop:abc"
        repo.create.return_value = None
        service = CalendarService(repo, provider)

        await service.create_event(user_ctx, "Dentista", datetime(2026, 8, 28, 17, 30, tzinfo=UTC))
        provider.create_event.assert_awaited_once()
        repo.create.assert_awaited_once()

    async def test_check_calendar(self, user_ctx):
        repo = AsyncMock()
        repo.list_range.return_value = []
        provider = NoopCalendarProvider()
        service = CalendarService(repo, provider)
        start = datetime(2026, 8, 24, tzinfo=UTC)
        end = datetime(2026, 8, 30, tzinfo=UTC)
        result = await service.check_calendar(user_ctx, start, end)
        assert result == []
        repo.list_range.assert_awaited_once_with("test-user", start, end)

    async def test_create_event_normalizes_naive_input_to_utc(self, user_ctx):
        """specs/023 T5.2/T5.5: 17:30 naive, Europe/Madrid winter (UTC+1) -> 16:30Z."""
        repo = AsyncMock()
        provider = AsyncMock(spec=NoopCalendarProvider)
        provider.create_event.return_value = "noop:abc"
        service = CalendarService(repo, provider)

        await service.create_event(user_ctx, "Dentista", datetime(2026, 1, 15, 17, 30))

        data = repo.create.call_args[0][1]
        assert data.start_at == datetime(2026, 1, 15, 16, 30, tzinfo=UTC)

    async def test_create_event_rejects_nonexistent_naive_input(self, user_ctx):
        """2026-03-29 02:30 doesn't exist in Europe/Madrid (DST spring-forward gap)."""
        repo = AsyncMock()
        provider = AsyncMock(spec=NoopCalendarProvider)
        service = CalendarService(repo, provider)

        with pytest.raises(AmbiguousOrNonExistentTimeError):
            await service.create_event(user_ctx, "x", datetime(2026, 3, 29, 2, 30))
        repo.create.assert_not_awaited()
