"""Unit tests for Reminder and Calendar services (mocked repos)."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.domain.calendar.models import CalendarEvent
from src.domain.calendar.provider import NoopCalendarProvider
from src.domain.calendar.service import CalendarService
from src.domain.preferences.timezone import AmbiguousOrNonExistentTimeError
from src.domain.reminders.models import Reminder
from src.domain.reminders.service import ReminderService
from src.domain.shared.recurrence import RecurrenceFrequency, RecurrenceRule
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


class TestSnoozeReminder:
    async def test_snooze_creates_followup_copy(self, user_ctx):
        original = Reminder(
            id=uuid4(), user_id="test-user", title="Cumpleaños", description=None,
            trigger_at=datetime(2026, 5, 10, 9, 0, tzinfo=UTC), status="fired",
            source_document_id=None, source_action_id=None,
            created_at=datetime(2026, 5, 10, tzinfo=UTC),
        )
        repo = AsyncMock()
        repo.get_by_id.return_value = original
        snoozed = original.model_copy(update={"id": uuid4(), "status": "pending"})
        repo.create_snoozed.return_value = snoozed
        service = ReminderService(repo)
        proposal_id = uuid4()

        before = datetime.now(tz=UTC)
        result = await service.snooze_reminder(user_ctx, original.id, 20, proposal_id)
        after = datetime.now(tz=UTC)

        assert result == snoozed
        repo.get_by_id.assert_awaited_once_with("test-user", original.id)
        repo.create_snoozed.assert_awaited_once()
        call = repo.create_snoozed.call_args[0]
        assert call[0] == original
        assert call[2] == proposal_id
        assert before + timedelta(minutes=20) <= call[1] <= after + timedelta(minutes=20)

    async def test_snooze_not_found_returns_none(self, user_ctx):
        repo = AsyncMock()
        repo.get_by_id.return_value = None
        service = ReminderService(repo)

        result = await service.snooze_reminder(user_ctx, uuid4(), 20, uuid4())
        assert result is None
        repo.create_snoozed.assert_not_awaited()

    async def test_snooze_minutes_out_of_bounds_rejected(self, user_ctx):
        repo = AsyncMock()
        service = ReminderService(repo)

        with pytest.raises(ValueError, match="minutes"):
            await service.snooze_reminder(user_ctx, uuid4(), 4, uuid4())
        repo.get_by_id.assert_not_awaited()


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


class TestCheckCalendarRecurrenceExpansion:
    async def test_past_anchor_yields_occurrence_in_current_range(self, user_ctx):
        anchor = CalendarEvent(
            id=uuid4(), user_id="test-user", title="Cumpleaños", description=None,
            location=None, start_at=datetime(2020, 3, 15, 10, 0, tzinfo=UTC), end_at=None,
            provider_event_id=None, source_document_id=None,
            created_at=datetime(2020, 1, 1, tzinfo=UTC),
            recurrence_rule=RecurrenceRule(frequency=RecurrenceFrequency.YEARLY),
        )
        repo = AsyncMock()
        repo.list_range.return_value = [anchor]
        service = CalendarService(repo, NoopCalendarProvider())

        result = await service.check_calendar(
            user_ctx, datetime(2026, 1, 1, tzinfo=UTC), datetime(2026, 12, 31, tzinfo=UTC)
        )

        assert len(result) == 1
        assert result[0].start_at == datetime(2026, 3, 15, 10, 0, tzinfo=UTC)
        assert result[0].id == anchor.id

    async def test_non_recurring_event_outside_range_excluded(self, user_ctx):
        event = CalendarEvent(
            id=uuid4(), user_id="test-user", title="Pasado", description=None,
            location=None, start_at=datetime(2020, 1, 1, tzinfo=UTC), end_at=None,
            provider_event_id=None, source_document_id=None,
            created_at=datetime(2020, 1, 1, tzinfo=UTC),
        )
        repo = AsyncMock()
        repo.list_range.return_value = [event]
        service = CalendarService(repo, NoopCalendarProvider())

        result = await service.check_calendar(
            user_ctx, datetime(2026, 1, 1, tzinfo=UTC), datetime(2026, 12, 31, tzinfo=UTC)
        )
        assert result == []

    async def test_recurrence_until_stops_expansion(self, user_ctx):
        anchor = CalendarEvent(
            id=uuid4(), user_id="test-user", title="Clase", description=None,
            location=None, start_at=datetime(2026, 1, 5, 9, 0, tzinfo=UTC), end_at=None,
            provider_event_id=None, source_document_id=None,
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
            recurrence_rule=RecurrenceRule(
                frequency=RecurrenceFrequency.WEEKLY,
                until=datetime(2026, 1, 12, 9, 0, tzinfo=UTC),
            ),
        )
        repo = AsyncMock()
        repo.list_range.return_value = [anchor]
        service = CalendarService(repo, NoopCalendarProvider())

        result = await service.check_calendar(
            user_ctx, datetime(2026, 1, 1, tzinfo=UTC), datetime(2026, 2, 1, tzinfo=UTC)
        )
        assert [e.start_at for e in result] == [
            datetime(2026, 1, 5, 9, 0, tzinfo=UTC), datetime(2026, 1, 12, 9, 0, tzinfo=UTC),
        ]
