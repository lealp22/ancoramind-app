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
