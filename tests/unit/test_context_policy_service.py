"""Unit tests for the pure history-selection policy (BL-34/specs/030 T3)."""

from __future__ import annotations

import pytest

from src.domain.context_policy.compaction import CompactionOutcome
from src.domain.context_policy.models import ContextBudgetConfig, ConversationTurn
from src.domain.context_policy.service import (
    available_history_tokens,
    estimate_turn_size_tokens,
    resolve_history_ceiling,
    resolve_num_history_runs,
    select_history_window,
)
from src.domain.runtime_config.models import ExecutionBudgetConfig, bootstrap_runtime_configuration


class _FakeCompactor:
    """Stands in for a real CompactionPort (specs/030 T5) — never invoked by
    select_history_window in this increment; only its presence/absence
    matters for the outcome it reports."""

    async def compact(
        self,
        turn_ids: tuple[str, ...],
        *,
        compacted_from_turn_id: str,
        compacted_to_turn_id: str,
    ) -> CompactionOutcome:
        return CompactionOutcome(
            summary_text="unused",
            compacted_from_turn_id=compacted_from_turn_id,
            compacted_to_turn_id=compacted_to_turn_id,
            status="unused",
        )


def _execution_budget(**changes) -> ExecutionBudgetConfig:
    base = bootstrap_runtime_configuration().execution_budget
    return base.model_copy(update=changes)


def _budget(**changes) -> ContextBudgetConfig:
    return ContextBudgetConfig.model_validate(
        {
            "reserved_for_instructions_tokens": 0,
            "reserved_for_current_message_tokens": 0,
            "reserved_for_tools_schema_tokens": 0,
            "safety_margin_tokens": 0,
            **changes,
        }
    )


def test_select_history_window_fits_entirely_when_small():
    turns = (
        ConversationTurn(turn_id="t1", estimated_tokens=100),
        ConversationTurn(turn_id="t2", estimated_tokens=100),
    )

    decision = select_history_window(turns, available_for_history_tokens=1000)

    assert decision.outcome == "fits_entirely"
    assert decision.kept_turn_ids == ("t1", "t2")
    assert decision.turns_to_compact == ()
    assert decision.kept_tokens == 200


def test_select_history_window_requires_compaction_for_older_turns():
    """specs/030 T5: ``needs_compaction`` only surfaces with a compactor configured."""
    turns = (
        ConversationTurn(turn_id="old-1", estimated_tokens=400),
        ConversationTurn(turn_id="old-2", estimated_tokens=400),
        ConversationTurn(turn_id="recent", estimated_tokens=400),
    )

    decision = select_history_window(
        turns, available_for_history_tokens=500, compactor=_FakeCompactor()
    )

    assert decision.outcome == "needs_compaction"
    assert decision.kept_turn_ids == ("recent",)
    assert decision.turns_to_compact == ("old-1", "old-2")
    assert decision.kept_tokens == 400


def test_select_history_window_degrades_to_truncated_without_a_compactor():
    """specs/030 T5 default: no CompactionPort configured => truncate, don't summarize."""
    turns = (
        ConversationTurn(turn_id="old-1", estimated_tokens=400),
        ConversationTurn(turn_id="old-2", estimated_tokens=400),
        ConversationTurn(turn_id="recent", estimated_tokens=400),
    )

    decision = select_history_window(turns, available_for_history_tokens=500)

    assert decision.outcome == "truncated"
    assert decision.kept_turn_ids == ("recent",)
    assert decision.turns_to_compact == ("old-1", "old-2")


def test_select_history_window_truncates_when_even_latest_turn_does_not_fit():
    turns = (ConversationTurn(turn_id="too-big", estimated_tokens=5000),)

    decision = select_history_window(turns, available_for_history_tokens=100)

    assert decision.outcome == "truncated"
    assert decision.kept_turn_ids == ()
    assert decision.turns_to_compact == ("too-big",)
    assert decision.kept_tokens == 0


def test_select_history_window_empty_history_fits_entirely():
    decision = select_history_window((), available_for_history_tokens=1000)

    assert decision.outcome == "fits_entirely"
    assert decision.kept_turn_ids == ()
    assert decision.turns_to_compact == ()


def test_resolve_num_history_runs_clamps_within_floor_and_ceiling():
    decision = select_history_window(
        tuple(ConversationTurn(turn_id=f"t{i}", estimated_tokens=10) for i in range(20)),
        available_for_history_tokens=1_000_000,
    )

    assert resolve_num_history_runs(decision, floor=1, ceiling=10) == 10


def test_resolve_num_history_runs_never_goes_below_floor():
    decision = select_history_window(
        (ConversationTurn(turn_id="too-big", estimated_tokens=5000),),
        available_for_history_tokens=100,
    )

    assert resolve_num_history_runs(decision, floor=1, ceiling=10) == 1


def test_available_history_tokens_subtracts_every_reservation():
    execution_budget = _execution_budget(max_output_tokens=1000)
    context_budget = _budget(
        reserved_for_instructions_tokens=100,
        reserved_for_current_message_tokens=200,
        reserved_for_tools_schema_tokens=300,
        safety_margin_tokens=400,
    )

    available = available_history_tokens(
        context_window_tokens=10_000,
        execution_budget=execution_budget,
        context_budget=context_budget,
    )

    assert available == 10_000 - 100 - 200 - 300 - 1000 - 400


def test_available_history_tokens_never_negative():
    execution_budget = _execution_budget(max_output_tokens=1000)

    available = available_history_tokens(
        context_window_tokens=500,
        execution_budget=execution_budget,
        context_budget=None,
    )

    assert available == 0


def test_estimate_turn_size_tokens_uses_real_output_budget_and_telegram_limit():
    execution_budget = _execution_budget(max_output_tokens=1024)

    assert estimate_turn_size_tokens(execution_budget) == 1024 + (4096 // 4)


@pytest.mark.parametrize("window", [None, 32_000, 128_000])
def test_resolve_history_ceiling_stays_within_floor_and_ceiling(window):
    execution_budget = _execution_budget()

    result = resolve_history_ceiling(
        context_window_tokens=window,
        execution_budget=execution_budget,
        context_budget=None,
        floor=1,
        ceiling=10,
    )

    assert 1 <= result <= 10


def test_resolve_history_ceiling_small_window_yields_smaller_ceiling_than_large():
    execution_budget = _execution_budget()

    small = resolve_history_ceiling(
        context_window_tokens=2_000,
        execution_budget=execution_budget,
        context_budget=None,
    )
    large = resolve_history_ceiling(
        context_window_tokens=128_000,
        execution_budget=execution_budget,
        context_budget=None,
    )

    assert small < large
