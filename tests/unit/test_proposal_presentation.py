"""Unit tests for proposal presentation and consent buttons (specs/023 T4.3-T4.4)."""

from __future__ import annotations

from uuid import uuid4

from src.domain.actions.presentation import (
    MAX_CALLBACK_DATA_BYTES,
    ConsentAction,
    consent_buttons,
    parse_consent_callback,
    render_proposal_block,
)


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
    block = render_proposal_block(uuid4(), "create_todo_item", {"title": "a\n" + "x" * 500})

    title_line = next(line for line in block.splitlines() if "Título" in line)
    assert "\n" not in title_line
    assert len(title_line) < 140
    assert title_line.endswith("…")


def test_unknown_tool_falls_back_to_its_name() -> None:
    assert "nueva_tool" in render_proposal_block(uuid4(), "nueva_tool", {})
