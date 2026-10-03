"""Round-trip timezone tests for reminders/calendar tools (specs/023 T5.5).

Covers the full chain a real request goes through: a naive local datetime
parsed by the tool -> normalized to UTC by the domain service (T5.2) ->
persisted (mocked repo) -> converted back to local for display (T5.3).
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

from agno.run import RunContext

from src.agent.tools import calendar, reminders
from src.agent.tools.validation import INVALID_PROPOSAL_DATA
from src.domain.calendar.models import CalendarEvent
from src.domain.calendar.provider import NoopCalendarProvider
from src.domain.calendar.service import CalendarService
from src.domain.reminders.models import Reminder
from src.domain.reminders.service import ReminderService

PROPOSAL_ID = "11111111-1111-1111-1111-111111111111"


def _run_context() -> RunContext:
    return RunContext(run_id="run-tz", session_id="tg:ancora:42", user_id="42")


class TestReminderTimezoneRoundTrip:
    async def test_naive_summer_input_persists_utc_and_displays_local(self, monkeypatch):
        """17:00 naive (Europe/Madrid, summer/UTC+2) -> persisted 15:00Z -> shown 17:00."""
        captured: dict[str, object] = {}

        async def fake_create(user_id, data):
            captured["trigger_at"] = data.trigger_at
            return Reminder(
                id=uuid4(), user_id=user_id, title=data.title, description=data.description,
                trigger_at=data.trigger_at, status="pending",
                source_document_id=data.source_document_id,
                source_action_id=data.source_action_id, created_at=datetime.now(tz=UTC),
            )

        repo = AsyncMock()
        repo.create.side_effect = fake_create
        service = ReminderService(repo)

        actions = AsyncMock()
        actions.confirm_or_use_confirmed.return_value = {
            "id": PROPOSAL_ID,
            "payload": {
                "title": "Llamar dentista",
                "trigger_at": "2026-08-28T17:00:00",
                "description": None,
                "source_document_id": None,
            },
        }

        monkeypatch.setattr(reminders, "_get_reminder_service", AsyncMock(return_value=service))
        monkeypatch.setattr(reminders, "_get_actions_repo", AsyncMock(return_value=actions))

        reply = await reminders.execute_reminder(_run_context(), PROPOSAL_ID)

        # Persisted instant is correct UTC (what the worker compares against).
        assert captured["trigger_at"] == datetime(2026, 8, 28, 15, 0, tzinfo=UTC)
        # Displayed back to the user, it reads as what they originally typed.
        assert "17:00" in reply
        assert "15:00" not in reply

    async def test_naive_dst_gap_rejected_before_persisting(self, monkeypatch):
        """2026-03-29 02:30 doesn't exist in Europe/Madrid (spring-forward gap)."""
        repo = AsyncMock()
        service = ReminderService(repo)
        actions = AsyncMock()
        actions.confirm_or_use_confirmed.return_value = {
            "id": PROPOSAL_ID,
            "payload": {
                "title": "x", "trigger_at": "2026-03-29T02:30:00",
                "description": None, "source_document_id": None,
            },
        }
        monkeypatch.setattr(reminders, "_get_reminder_service", AsyncMock(return_value=service))
        monkeypatch.setattr(reminders, "_get_actions_repo", AsyncMock(return_value=actions))

        reply = await reminders.execute_reminder(_run_context(), PROPOSAL_ID)

        repo.create.assert_not_awaited()
        assert reply == INVALID_PROPOSAL_DATA

    async def test_list_reminders_converts_stored_utc_back_to_local(self, monkeypatch):
        reminder = Reminder(
            id=uuid4(), user_id="42", title="ITV", description=None,
            trigger_at=datetime(2026, 1, 15, 16, 30, tzinfo=UTC),  # winter, UTC+1
            status="pending", source_document_id=None, source_action_id=None,
            created_at=datetime.now(tz=UTC),
        )
        service = AsyncMock()
        service.list_reminders.return_value = [reminder]
        monkeypatch.setattr(reminders, "_get_reminder_service", AsyncMock(return_value=service))

        reply = await reminders.list_reminders(_run_context())

        assert "17:30" in reply
        assert "16:30" not in reply


class TestCalendarTimezoneRoundTrip:
    async def test_naive_winter_input_persists_utc_and_displays_local(self, monkeypatch):
        """17:30 naive (Europe/Madrid, winter/UTC+1) -> persisted 16:30Z -> shown 17:30."""
        captured: dict[str, object] = {}

        async def fake_create(user_id, data, provider_id):
            captured["start_at"] = data.start_at
            return CalendarEvent(
                id=uuid4(), user_id=user_id, title=data.title, description=data.description,
                location=data.location, start_at=data.start_at, end_at=data.end_at,
                provider_event_id=provider_id, source_document_id=data.source_document_id,
                created_at=datetime.now(tz=UTC),
            )

        repo = AsyncMock()
        repo.create.side_effect = fake_create
        service = CalendarService(repo, NoopCalendarProvider())

        actions = AsyncMock()
        actions.confirm_or_use_confirmed.return_value = {
            "id": PROPOSAL_ID,
            "payload": {
                "title": "Dentista", "start_at": "2026-01-15T17:30:00", "end_at": None,
                "description": None, "location": None, "source_document_id": None,
            },
        }

        monkeypatch.setattr(calendar, "_get_calendar_service", AsyncMock(return_value=service))
        monkeypatch.setattr(calendar, "_get_actions_repo", AsyncMock(return_value=actions))

        reply = await calendar.execute_calendar_event(_run_context(), PROPOSAL_ID)

        assert captured["start_at"] == datetime(2026, 1, 15, 16, 30, tzinfo=UTC)
        assert "17:30" in reply
        assert "16:30" not in reply

    async def test_naive_dst_ambiguous_fall_back_rejected_before_persisting(self, monkeypatch):
        """2026-10-25 02:30 occurs twice in Europe/Madrid (fall-back overlap)."""
        repo = AsyncMock()
        service = CalendarService(repo, NoopCalendarProvider())
        actions = AsyncMock()
        actions.confirm_or_use_confirmed.return_value = {
            "id": PROPOSAL_ID,
            "payload": {
                "title": "x", "start_at": "2026-10-25T02:30:00", "end_at": None,
                "description": None, "location": None, "source_document_id": None,
            },
        }
        monkeypatch.setattr(calendar, "_get_calendar_service", AsyncMock(return_value=service))
        monkeypatch.setattr(calendar, "_get_actions_repo", AsyncMock(return_value=actions))

        reply = await calendar.execute_calendar_event(_run_context(), PROPOSAL_ID)

        repo.create.assert_not_awaited()
        assert reply == INVALID_PROPOSAL_DATA


class TestCheckCalendarDisplay:
    async def test_check_calendar_converts_stored_utc_back_to_local(self, monkeypatch):
        event = CalendarEvent(
            id=uuid4(), user_id="42", title="Dentista", description=None, location=None,
            start_at=datetime(2026, 8, 24, 15, 30, tzinfo=UTC),  # summer, UTC+2
            end_at=None, provider_event_id="noop:x", source_document_id=None,
            created_at=datetime.now(tz=UTC),
        )
        service = AsyncMock()
        service.check_calendar.return_value = [event]
        monkeypatch.setattr(calendar, "_get_calendar_service", AsyncMock(return_value=service))

        reply = await calendar.check_calendar(_run_context(), "2026-08-24T00:00:00")

        assert "17:30" in reply
        assert "15:30" not in reply
