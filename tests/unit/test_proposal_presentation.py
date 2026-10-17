"""Unit tests for proposal presentation and consent buttons (specs/023 T4.3-T4.4)."""

from __future__ import annotations

from uuid import uuid4

import pytest

from src.domain.actions.models import payload_hash
from src.domain.actions.presentation import (
    MAX_CALLBACK_DATA_BYTES,
    ConsentAction,
    consent_buttons,
    parse_consent_callback,
    render_proposal_block,
)
from src.notifications.markup import markdown_to_telegram_html


def test_buttons_round_trip_and_fit_telegram_limit() -> None:
    proposal_id = uuid4()
    confirm, discard = consent_buttons(proposal_id)

    assert confirm.label == "✅ Sí" and discard.label == "❌ No"
    for button, action in ((confirm, ConsentAction.CONFIRM), (discard, ConsentAction.DISCARD)):
        assert len(button.callback_data.encode()) <= MAX_CALLBACK_DATA_BYTES
        parsed = parse_consent_callback(button.callback_data)
        assert parsed is not None
        assert parsed.action is action and parsed.proposal_id == proposal_id


def test_only_exact_button_payloads_are_recognised() -> None:
    proposal_id = uuid4()
    for data in (
        None,
        "",
        "si",
        f"x:{proposal_id}",
        f"c:{proposal_id} extra",
        f" c:{proposal_id}",
        "c:not-a-uuid",
        "c:" + "a" * 80,
    ):
        assert parse_consent_callback(data) is None


def test_block_is_built_from_the_stored_payload_only() -> None:
    proposal_id = uuid4()
    block = render_proposal_block(
        proposal_id,
        "create_reminder",
        {
            "title": "ITV",
            "trigger_at": "2026-10-20T09:00:00",
            "description": None,
            "source_document_id": "should-not-appear",
        },
    )

    assert "Crear recordatorio" in block
    assert "Título: ITV" in block
    assert "Cuándo: 2026-10-20T09:00:00" in block
    assert str(proposal_id) not in block
    assert "ID:" not in block
    assert "Descripción" not in block
    assert "should-not-appear" not in block


def test_block_bounds_and_flattens_long_values() -> None:
    payload = {"title": "a\n" + "x" * 500}
    before = payload_hash("create_todo_item", payload)
    block = render_proposal_block(uuid4(), "create_todo_item", payload)

    title_line = next(line for line in block.splitlines() if "Título" in line)
    assert "\n" not in title_line
    assert len(title_line) < 140
    assert title_line.endswith("…")
    assert payload_hash("create_todo_item", payload) == before


def test_unknown_tool_falls_back_to_its_name() -> None:
    assert "nueva_tool" in render_proposal_block(uuid4(), "nueva_tool", {})


@pytest.mark.parametrize(
    "stored,display", [("high", "alta"), ("normal", "normal"), ("low", "baja")]
)
def test_priorities_are_translated_without_changing_payload(stored, display) -> None:
    payload = {"title": "Seguro", "priority": stored}
    before = payload_hash("create_todo_item", payload)
    block = render_proposal_block(uuid4(), "create_todo_item", payload)
    assert f"Prioridad: {display}" in block
    assert payload["priority"] == stored
    assert payload_hash("create_todo_item", payload) == before


@pytest.mark.parametrize("tool", ["create_todo_item", "update_todo_item"])
@pytest.mark.parametrize("stored", ["2026-10-20", "2026-10-20T00:00:00"])
def test_todo_due_date_is_readable_without_mutating_payload(tool, stored) -> None:
    payload = {"due_date": stored}
    before = payload_hash(tool, payload)
    block = render_proposal_block(uuid4(), tool, payload)
    assert "Fecha límite: 20 de octubre de 2026" in block
    assert "T00:00:00" not in block
    assert payload["due_date"] == stored
    assert payload_hash(tool, payload) == before


@pytest.mark.parametrize(
    "stored,time_text",
    [
        ("2026-10-20T16:30:01", "16:30:01"),
        ("2026-10-20T00:00:00+02:00", "00:00:00+02:00"),
        ("2026-10-20T00:00:00Z", "00:00:00+00:00"),
        ("2026-10-20T00:00:00.000123", "00:00:00.000123"),
        ("2026-10-20T23:59:59.999999-03:30", "23:59:59.999999-03:30"),
        ("2026-10-20T00:00:00.000123+05:45", "00:00:00.000123+05:45"),
    ],
)
def test_todo_explicit_times_and_offsets_are_preserved(stored, time_text) -> None:
    payload = {"due_date": stored}
    before = payload_hash("create_todo_item", payload)
    block = render_proposal_block(uuid4(), "create_todo_item", payload)
    assert f"Fecha límite: 20 de octubre de 2026, {time_text}" in block
    assert payload["due_date"] == stored
    assert payload_hash("create_todo_item", payload) == before


@pytest.mark.parametrize(
    "tool,key", [("create_reminder", "trigger_at"), ("create_calendar_event", "start_at")]
)
def test_midnight_reminder_and_event_are_not_reinterpreted_as_date_only(tool, key) -> None:
    stored = "2026-10-20T00:00:00+02:00"
    payload = {key: stored}
    before = payload_hash(tool, payload)
    assert stored in render_proposal_block(uuid4(), tool, payload)
    assert payload_hash(tool, payload) == before


def test_unexpected_values_fall_back_and_html_stays_escaped() -> None:
    payload = {"title": "<script>DATA</script>", "priority": "unknown", "due_date": "not a date"}
    before = payload_hash("create_todo_item", payload)
    block = render_proposal_block(uuid4(), "create_todo_item", payload)
    assert "Prioridad: unknown" in block
    assert "Fecha límite: not a date" in block
    html = markdown_to_telegram_html(block)
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
    assert payload_hash("create_todo_item", payload) == before


@pytest.mark.parametrize(
    "frequency,interval,display",
    [
        ("daily", 1, "cada 1 día"),
        ("daily", 3, "cada 3 días"),
        ("weekly", 1, "cada 1 semana"),
        ("weekly", 2, "cada 2 semanas"),
        ("monthly", 1, "cada 1 mes"),
        ("monthly", 6, "cada 6 meses"),
        ("yearly", 1, "cada 1 año"),
        ("yearly", 2, "cada 2 años"),
    ],
)
def test_calendar_recurrence_is_reviewable_without_changing_payload(
    frequency, interval, display
) -> None:
    payload = {
        "title": "Clase",
        "start_at": "2026-10-20T00:00:00+02:00",
        "end_at": "2026-10-20T01:00:00+02:00",
        "recurrence_frequency": frequency,
        "recurrence_interval": interval,
        "recurrence_until": "2027-10-20T00:00:00+02:00",
        "with_reminder": True,
        "reminder_lead_minutes": 90,
    }
    before = payload_hash("create_calendar_event", payload)
    block = render_proposal_block(uuid4(), "create_calendar_event", payload)
    assert f"Repetición: {display}" in block
    assert "Repetir hasta (inclusive): 2027-10-20T00:00:00+02:00" in block
    assert "Aviso: sí" in block
    assert "Antelación: 1 h 30 min antes del inicio" in block
    assert f"Inicio: {payload['start_at']}" in block
    assert f"Fin: {payload['end_at']}" in block
    assert block.count("Pulsa ✅ Sí") == 1
    assert payload_hash("create_calendar_event", payload) == before


@pytest.mark.parametrize("payload", [{}, {"recurrence_frequency": None, "with_reminder": False}])
def test_one_off_calendar_explicitly_has_no_recurrence_or_reminder(payload) -> None:
    block = render_proposal_block(uuid4(), "create_calendar_event", payload)
    assert "Repetición: no se repite" in block
    assert "Aviso: no" in block
    assert "Antelación" not in block
    assert "Repetir hasta" not in block


@pytest.mark.parametrize("interval", [None, 1])
def test_calendar_open_ended_recurrence_and_execution_defaults(interval) -> None:
    block = render_proposal_block(
        uuid4(), "create_calendar_event",
        {"recurrence_frequency": "weekly", "recurrence_interval": interval, "with_reminder": True},
    )
    assert "Repetición: cada 1 semana" in block
    assert "Repetir hasta (inclusive): sin fecha límite" in block
    assert "Aviso: sí" in block
    assert "Antelación: al inicio" in block


@pytest.mark.parametrize(
    "minutes,display",
    [(0, "al inicio"), (5, "5 min antes del inicio"), (60, "1 h antes del inicio")],
)
def test_calendar_reminder_lead_is_not_hidden_when_zero(minutes, display) -> None:
    block = render_proposal_block(
        uuid4(), "create_calendar_event",
        {"with_reminder": True, "reminder_lead_minutes": minutes},
    )
    assert f"Antelación: {display}" in block


@pytest.mark.parametrize(
    "minutes,display", [(5, "5 min"), (60, "1 h"), (90, "1 h 30 min"), (10080, "168 h")]
)
def test_snooze_displays_canonical_target_and_duration_without_changing_hash(
    minutes, display
) -> None:
    payload = {"reminder_id": str(uuid4()), "minutes": minutes, "title": "LLM title ignored"}
    before = payload_hash("snooze_reminder", payload)
    block = render_proposal_block(
        uuid4(), "snooze_reminder", payload, reminder_title="Revisar seguro",
    )
    assert "Propuesta**: Posponer recordatorio" in block
    assert "Recordatorio: Revisar seguro" in block
    assert f"Aplazamiento: {display} desde la confirmación" in block
    assert "LLM title ignored" not in block
    assert payload["reminder_id"] not in block
    assert payload_hash("snooze_reminder", payload) == before


def test_snooze_without_canonical_target_does_not_invent_one() -> None:
    block = render_proposal_block(
        uuid4(), "snooze_reminder", {"minutes": 20, "title": "Unverified"},
    )
    assert "Recordatorio: No disponible" in block
    assert "Unverified" not in block
    assert "Aplazamiento: 20 min desde la confirmación" in block


def test_snooze_target_is_bounded_flattened_and_html_escaped() -> None:
    block = render_proposal_block(
        uuid4(), "snooze_reminder", {"minutes": 20},
        reminder_title="<script>DATA</script>\n" + "x" * 500,
    )
    target_line = next(line for line in block.splitlines() if "Recordatorio:" in line)
    assert target_line.endswith("…")
    assert len(target_line) < 140
    html = markdown_to_telegram_html(block)
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def test_calendar_does_not_present_ignored_recurrence_or_reminder_fields() -> None:
    block = render_proposal_block(
        uuid4(), "create_calendar_event",
        {"recurrence_frequency": None, "recurrence_interval": 5,
         "recurrence_until": "IGNORED", "with_reminder": False, "reminder_lead_minutes": 30},
    )
    assert "Repetición: no se repite" in block
    assert "IGNORED" not in block
    assert "Repetir hasta" not in block
    assert "Aviso: no" in block
    assert "Antelación" not in block


def test_calendar_added_fields_stay_bounded_and_unknown_frequency_is_not_reinterpreted() -> None:
    block = render_proposal_block(
        uuid4(), "create_calendar_event",
        {"recurrence_frequency": "unexpected", "recurrence_interval": 0,
         "recurrence_until": "<script>\n" + "x" * 500,
         "with_reminder": True, "reminder_lead_minutes": "invalid"},
    )
    assert "Repetición: cada 0 unexpected" in block
    assert "Antelación: invalid antes del inicio" in block
    until_line = next(line for line in block.splitlines() if "Repetir hasta" in line)
    assert until_line.endswith("…")
    assert "<script>" not in markdown_to_telegram_html(block)
