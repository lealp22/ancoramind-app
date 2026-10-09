"""Unit tests for pure context-window policy models (BL-34/specs/030 T1)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.domain.context_policy.models import (
    ContextBudgetConfig,
    ConversationTurn,
    estimate_tokens,
)


def test_estimate_tokens_empty_text_is_zero():
    assert estimate_tokens("") == 0


def test_estimate_tokens_uses_four_chars_per_token_heuristic():
    assert estimate_tokens("abcd") == 1
    assert estimate_tokens("abcdefgh") == 2
    assert estimate_tokens("abc") == 0  # integer division, documented limit


def test_estimate_tokens_counts_unicode_code_points_not_bytes():
    # "é" x4 is 4 code points regardless of its UTF-8 byte length.
    assert estimate_tokens("éééé") == 1


def test_estimate_tokens_long_text():
    text = "x" * 4001
    assert estimate_tokens(text) == 1000


def _budget(**changes):
    return ContextBudgetConfig.model_validate(
        {
            "reserved_for_instructions_tokens": 200,
            "reserved_for_current_message_tokens": 400,
            "reserved_for_tools_schema_tokens": 300,
            "safety_margin_tokens": 100,
            **changes,
        }
    )


def test_context_budget_config_accepts_valid_values():
    budget = _budget()
    assert budget.reserved_for_instructions_tokens == 200
    assert budget.safety_margin_tokens == 100


def test_context_budget_config_is_frozen():
    budget = _budget()
    with pytest.raises(ValidationError):
        budget.safety_margin_tokens = 999  # type: ignore[misc]


@pytest.mark.parametrize(
    "field",
    [
        "reserved_for_instructions_tokens",
        "reserved_for_current_message_tokens",
        "reserved_for_tools_schema_tokens",
        "safety_margin_tokens",
    ],
)
def test_context_budget_config_rejects_negative_values(field):
    with pytest.raises(ValidationError):
        _budget(**{field: -1})


def test_context_budget_config_rejects_unknown_fields():
    with pytest.raises(ValidationError):
        _budget(unexpected_field=1)


def test_conversation_turn_accepts_valid_values():
    turn = ConversationTurn(turn_id="turn-1", estimated_tokens=50)
    assert turn.turn_id == "turn-1"
    assert turn.estimated_tokens == 50


def test_conversation_turn_rejects_empty_turn_id():
    with pytest.raises(ValueError, match="turn_id must not be empty"):
        ConversationTurn(turn_id="", estimated_tokens=10)


def test_conversation_turn_rejects_negative_estimated_tokens():
    with pytest.raises(ValueError, match="estimated_tokens must not be negative"):
        ConversationTurn(turn_id="turn-1", estimated_tokens=-1)
