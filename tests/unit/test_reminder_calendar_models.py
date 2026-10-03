"""Unit tests for Reminder and Calendar domain models."""

from datetime import UTC, datetime
from uuid import uuid4

from src.domain.calendar.models import CalendarEvent, CalendarEventCreate
from src.domain.reminders.models import Reminder, ReminderCreate
from src.domain.shared.recurrence import RecurrenceFrequency, RecurrenceRule


class TestReminderCreate:
    def test_valid(self):
        rc = ReminderCreate(
            title="Llamar dentista", trigger_at=datetime(2026, 8, 28, 17, 0, tzinfo=UTC)
        )
        assert rc.title == "Llamar dentista"
        assert rc.status if hasattr(rc, "status") else True

    def test_empty_title_fails(self):
        import pytest
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            ReminderCreate(title="", trigger_at=datetime(2026, 8, 28, tzinfo=UTC))

    def test_naive_trigger_at_rejected(self):
        """specs/023 T5.2: a naive datetime must be normalized before this model."""
        import pytest
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            ReminderCreate(title="t", trigger_at=datetime(2026, 8, 28, 17, 0))


class TestReminder:
    def test_from_attributes(self):
        r = Reminder(id=uuid4(), user_id="u1", title="t", description=None,
                     trigger_at=datetime(2026, 8, 28, tzinfo=UTC),
                     status="pending", source_document_id=None, source_action_id=None,
                     created_at=datetime(2026, 8, 24, tzinfo=UTC))
        assert r.status == "pending"
        assert r.user_id == "u1"
        assert r.recurrence_rule is None
        assert r.fired_at is None

    def test_recurrence_rule_accepted_as_dict(self):
        """JSONB columns come back as a plain dict — Pydantic parses it directly."""
        r = Reminder(id=uuid4(), user_id="u1", title="t", description=None,
                     trigger_at=datetime(2026, 8, 28, tzinfo=UTC),
                     status="pending", source_document_id=None, source_action_id=None,
                     created_at=datetime(2026, 8, 24, tzinfo=UTC),
                     recurrence_rule={"frequency": "yearly", "interval": 1, "until": None})
        assert r.recurrence_rule == RecurrenceRule(frequency=RecurrenceFrequency.YEARLY)


class TestReminderCreateRecurrence:
    def test_recurrence_rule_optional(self):
        rc = ReminderCreate(
            title="Cumpleaños", trigger_at=datetime(2026, 5, 10, tzinfo=UTC),
            recurrence_rule=RecurrenceRule(frequency=RecurrenceFrequency.YEARLY),
        )
        assert rc.recurrence_rule is not None
        assert rc.recurrence_rule.frequency == RecurrenceFrequency.YEARLY


class TestCalendarEventCreate:
    def test_valid(self):
        ce = CalendarEventCreate(
            title="Dentista", start_at=datetime(2026, 8, 28, 17, 30, tzinfo=UTC)
        )
        assert ce.title == "Dentista"
        assert ce.end_at is None

    def test_naive_start_at_rejected(self):
        """specs/023 T5.2: a naive datetime must be normalized before this model."""
        import pytest
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            CalendarEventCreate(title="Dentista", start_at=datetime(2026, 8, 28, 17, 30))


class TestCalendarEvent:
    def test_from_attributes(self):
        e = CalendarEvent(id=uuid4(), user_id="u1", title="Dentista",
                          description=None, location=None,
                          start_at=datetime(2026, 8, 28, 17, 30, tzinfo=UTC),
                          end_at=None, provider_event_id="noop:test",
                          source_document_id=None,
                          created_at=datetime(2026, 8, 24, tzinfo=UTC))
        assert e.provider_event_id == "noop:test"
        assert e.recurrence_rule is None

    def test_recurrence_rule_accepted_as_dict(self):
        e = CalendarEvent(id=uuid4(), user_id="u1", title="Cumpleaños",
                          description=None, location=None,
                          start_at=datetime(2026, 3, 15, tzinfo=UTC),
                          end_at=None, provider_event_id="noop:test",
                          source_document_id=None,
                          created_at=datetime(2026, 1, 1, tzinfo=UTC),
                          recurrence_rule={"frequency": "yearly", "interval": 1, "until": None})
        assert e.recurrence_rule == RecurrenceRule(frequency=RecurrenceFrequency.YEARLY)
