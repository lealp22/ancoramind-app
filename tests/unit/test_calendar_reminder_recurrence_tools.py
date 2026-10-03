"""Tool-layer tests for recurrence + snooze (specs/024).

Covers: payload round-trip (propose -> stored payload -> execute re-parse)
for calendar recurrence + linked reminder, reminder recurrence, and the new
reminder-snooze pair; plus the mandatory security test that ownership checks
use UserContext, never the LLM-controlled payload.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

from agno.run import RunContext

from src.agent.tools import calendar, reminders
from src.domain.calendar.models import CalendarEvent
from src.domain.calendar.provider import NoopCalendarProvider
from src.domain.calendar.service import CalendarService
from src.domain.reminders.models import Reminder
from src.domain.reminders.service import ReminderService

PROPOSAL_ID = "11111111-1111-1111-1111-111111111111"
OTHER_USER_REMINDER_ID = "22222222-2222-2222-2222-222222222222"


def _run_context(user_id: str = "42") -> RunContext:
    return RunContext(run_id="run-1", session_id=f"tg:ancora:{user_id}", user_id=user_id)


class TestProposeCalendarEventRecurrence:
    async def test_payload_includes_recurrence_and_reminder_link(self, monkeypatch):
        actions = AsyncMock()
        actions.create.return_value = {"id": PROPOSAL_ID}
        monkeypatch.setattr(calendar, "_get_actions_repo", AsyncMock(return_value=actions))

        reply = await calendar.propose_calendar_event(
            _run_context(), "Cumpleaños", "2026-03-15T10:00:00",
            recurrence_frequency="yearly", with_reminder=True, reminder_lead_minutes=60,
        )

        payload = actions.create.call_args.kwargs["payload"]
        assert payload["recurrence_frequency"] == "yearly"
        assert payload["recurrence_interval"] == 1
        assert payload["with_reminder"] is True
        assert payload["reminder_lead_minutes"] == 60
        assert "🔁" in reply
        assert "recordatorio vinculado" in reply.lower()

    async def test_invalid_recurrence_frequency_rejected_before_proposal(self, monkeypatch):
        actions = AsyncMock()
        monkeypatch.setattr(calendar, "_get_actions_repo", AsyncMock(return_value=actions))

        reply = await calendar.propose_calendar_event(
            _run_context(), "x", "2026-03-15T10:00:00", recurrence_frequency="fortnightly",
        )

        assert "no válida" in reply
        actions.create.assert_not_awaited()


class TestExecuteCalendarEventCreatesLinkedReminder:
    async def test_execute_creates_event_and_linked_reminder(self, monkeypatch):
        event = CalendarEvent(
            id=uuid4(), user_id="42", title="Cumpleaños", description=None, location=None,
            start_at=datetime(2026, 3, 15, 10, 0, tzinfo=UTC), end_at=None,
            provider_event_id="noop:x", source_document_id=None,
            created_at=datetime.now(tz=UTC),
        )
        cal_repo = AsyncMock()
        cal_repo.create.return_value = event
        cal_service = CalendarService(cal_repo, NoopCalendarProvider())

        reminder = Reminder(
            id=uuid4(), user_id="42", title="Recordatorio: Cumpleaños", description=None,
            trigger_at=datetime(2026, 3, 15, 9, 0, tzinfo=UTC), status="pending",
            source_document_id=None, source_action_id=None, created_at=datetime.now(tz=UTC),
        )
        rem_repo = AsyncMock()
        rem_repo.create.return_value = reminder
        rem_service = ReminderService(rem_repo)

        actions = AsyncMock()
        actions.confirm_or_use_confirmed.return_value = {
            "id": PROPOSAL_ID,
            "payload": {
                "title": "Cumpleaños", "start_at": "2026-03-15T10:00:00", "end_at": None,
                "description": None, "location": None, "source_document_id": None,
                "with_reminder": True, "reminder_lead_minutes": 60,
                "recurrence_frequency": "yearly", "recurrence_interval": 1,
                "recurrence_until": None,
            },
        }
        monkeypatch.setattr(calendar, "_get_calendar_service", AsyncMock(return_value=cal_service))
        monkeypatch.setattr(calendar, "_get_reminder_service", AsyncMock(return_value=rem_service))
        monkeypatch.setattr(calendar, "_get_actions_repo", AsyncMock(return_value=actions))

        reply = await calendar.execute_calendar_event(_run_context(), PROPOSAL_ID)

        assert "Evento añadido" in reply
        assert "Recordatorio vinculado creado" in reply
        rem_data = rem_repo.create.call_args[0][1]
        assert rem_data.recurrence_rule is not None
        assert rem_data.recurrence_rule.frequency.value == "yearly"
        # Lead time: 60 minutes before the event's 10:00 start.
        assert rem_data.trigger_at == datetime(2026, 3, 15, 9, 0, tzinfo=UTC)

    async def test_linked_reminder_failure_does_not_hide_event_success(self, monkeypatch):
        event = CalendarEvent(
            id=uuid4(), user_id="42", title="Evento", description=None, location=None,
            start_at=datetime(2026, 3, 15, 10, 0, tzinfo=UTC), end_at=None,
            provider_event_id="noop:x", source_document_id=None,
            created_at=datetime.now(tz=UTC),
        )
        cal_repo = AsyncMock()
        cal_repo.create.return_value = event
        cal_service = CalendarService(cal_repo, NoopCalendarProvider())

        rem_service = AsyncMock()
        rem_service.create_reminder.side_effect = RuntimeError("db down")

        actions = AsyncMock()
        actions.confirm_or_use_confirmed.return_value = {
            "id": PROPOSAL_ID,
            "payload": {
                "title": "Evento", "start_at": "2026-03-15T10:00:00", "end_at": None,
                "description": None, "location": None, "source_document_id": None,
                "with_reminder": True, "reminder_lead_minutes": 0,
                "recurrence_frequency": None, "recurrence_interval": None,
                "recurrence_until": None,
            },
        }
        monkeypatch.setattr(calendar, "_get_calendar_service", AsyncMock(return_value=cal_service))
        monkeypatch.setattr(calendar, "_get_reminder_service", AsyncMock(return_value=rem_service))
        monkeypatch.setattr(calendar, "_get_actions_repo", AsyncMock(return_value=actions))

        reply = await calendar.execute_calendar_event(_run_context(), PROPOSAL_ID)

        assert "Evento añadido" in reply
        assert "no se pudo crear el recordatorio" in reply.lower()


class TestReminderSnoozeTools:
    async def test_propose_snooze_rejects_out_of_bounds_hours(self, monkeypatch):
        actions = AsyncMock()
        monkeypatch.setattr(reminders, "_get_actions_repo", AsyncMock(return_value=actions))

        reply = await reminders.propose_reminder_snooze(_run_context(), str(uuid4()), 100)

        assert "entre 1 y 72" in reply
        actions.create.assert_not_awaited()

    async def test_propose_snooze_creates_proposal(self, monkeypatch):
        actions = AsyncMock()
        actions.create.return_value = {"id": PROPOSAL_ID}
        monkeypatch.setattr(reminders, "_get_actions_repo", AsyncMock(return_value=actions))
        reminder_id = str(uuid4())

        reply = await reminders.propose_reminder_snooze(_run_context(), reminder_id, 3)

        assert "aplazamiento" in reply.lower()
        payload = actions.create.call_args.kwargs["payload"]
        assert payload == {"reminder_id": reminder_id, "hours": 3}
        assert actions.create.call_args.kwargs["tool_name"] == "snooze_reminder"

    async def test_execute_snooze_creates_followup_reminder(self, monkeypatch):
        snoozed = Reminder(
            id=uuid4(), user_id="42", title="Cumpleaños", description=None,
            trigger_at=datetime.now(tz=UTC), status="pending",
            source_document_id=None, source_action_id=None, created_at=datetime.now(tz=UTC),
        )
        service = AsyncMock()
        service.snooze_reminder.return_value = snoozed
        actions = AsyncMock()
        actions.confirm_or_use_confirmed.return_value = {
            "id": PROPOSAL_ID, "payload": {"reminder_id": str(uuid4()), "hours": 3},
        }
        monkeypatch.setattr(reminders, "_get_reminder_service", AsyncMock(return_value=service))
        monkeypatch.setattr(reminders, "_get_actions_repo", AsyncMock(return_value=actions))

        reply = await reminders.execute_reminder_snooze(_run_context(), PROPOSAL_ID)

        assert "aplazado" in reply.lower()
        actions.mark_executed.assert_awaited_once()

    async def test_execute_snooze_not_found_returns_message_without_marking_executed(
        self, monkeypatch
    ):
        service = AsyncMock()
        service.snooze_reminder.return_value = None
        actions = AsyncMock()
        actions.confirm_or_use_confirmed.return_value = {
            "id": PROPOSAL_ID, "payload": {"reminder_id": str(uuid4()), "hours": 3},
        }
        monkeypatch.setattr(reminders, "_get_reminder_service", AsyncMock(return_value=service))
        monkeypatch.setattr(reminders, "_get_actions_repo", AsyncMock(return_value=actions))

        reply = await reminders.execute_reminder_snooze(_run_context(), PROPOSAL_ID)

        assert "no se encontró" in reply.lower()
        actions.mark_executed.assert_not_awaited()

    async def test_execute_snooze_ownership_comes_from_user_context_not_payload(
        self, monkeypatch
    ):
        """Security: the user scoping snooze_reminder is the channel's
        UserContext (from run_context), never anything from the stored
        payload — the payload only carries which reminder + how long.
        """
        service = AsyncMock()
        service.snooze_reminder.return_value = None
        actions = AsyncMock()
        actions.confirm_or_use_confirmed.return_value = {
            "id": PROPOSAL_ID,
            "payload": {"reminder_id": OTHER_USER_REMINDER_ID, "hours": 3},
        }
        monkeypatch.setattr(reminders, "_get_reminder_service", AsyncMock(return_value=service))
        monkeypatch.setattr(reminders, "_get_actions_repo", AsyncMock(return_value=actions))

        await reminders.execute_reminder_snooze(_run_context(user_id="42"), PROPOSAL_ID)

        call_kwargs = service.snooze_reminder.call_args.kwargs
        assert call_kwargs["user_context"].user_id == "42"
        actions.confirm_or_use_confirmed.assert_awaited_once_with("42", PROPOSAL_ID)
