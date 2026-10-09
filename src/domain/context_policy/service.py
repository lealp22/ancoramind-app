"""Pure history-selection policy — no Agno, no I/O (BL-34/specs/030 T3).

Deliberately does not read Agno's real session/history: GovernedAgentFactory
(T4) only ever passes an integer ``num_history_runs`` ceiling to Agno, so
this module approximates how many past turns fit the available budget by
turn *size*, never by reading the actual session table (spec.md §6).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

from src.domain.context_policy.models import (
    ContextBudgetConfig,
    ContextWindowDecision,
    ContextWindowOutcome,
    ConversationTurn,
    estimate_tokens,
)
from src.notifications.markup import MAX_MESSAGE_CHARS

if TYPE_CHECKING:
    from src.domain.context_policy.compaction import CompactionPort
    from src.domain.runtime_config.models import ExecutionBudgetConfig

#: Fallback when a route has no declared window (spec.md §5.1): conservative
#: on purpose — assume a small model rather than risk overflowing a real one.
DEFAULT_CONTEXT_WINDOW_TOKENS = 8192

_ZERO_RESERVES = ContextBudgetConfig(
    reserved_for_instructions_tokens=0,
    reserved_for_current_message_tokens=0,
    reserved_for_tools_schema_tokens=0,
    safety_margin_tokens=0,
)


def available_history_tokens(
    *,
    context_window_tokens: int | None,
    execution_budget: ExecutionBudgetConfig,
    context_budget: ContextBudgetConfig | None,
) -> int:
    """Return the token budget left for history after every reservation."""
    window = (
        context_window_tokens
        if context_window_tokens is not None
        else DEFAULT_CONTEXT_WINDOW_TOKENS
    )
    budget = context_budget if context_budget is not None else _ZERO_RESERVES
    return max(
        0,
        window
        - budget.reserved_for_instructions_tokens
        - budget.reserved_for_current_message_tokens
        - budget.reserved_for_tools_schema_tokens
        - execution_budget.max_output_tokens
        - budget.safety_margin_tokens,
    )


def select_history_window(
    turns: Sequence[ConversationTurn],
    *,
    available_for_history_tokens: int,
    compactor: CompactionPort | None = None,
) -> ContextWindowDecision:
    """Keep the most recent turns that fit; older ones go to compaction/truncation.

    ``turns`` is ordered oldest-first (matching ConversationTurn's own
    ordering convention). The policy never inspects turn content — only the
    pre-estimated size the caller already attached to each turn.

    ``compactor`` is accepted for forward compatibility only (specs/030 T5):
    no implementation is invoked here. When older turns remain and no
    ``compactor`` is given — the only case in this increment — the outcome
    degrades from ``needs_compaction`` to ``truncated`` (spec.md §7).
    """
    kept_ids: list[str] = []
    kept_tokens = 0
    cursor = len(turns)
    for turn in reversed(turns):
        candidate_tokens = kept_tokens + turn.estimated_tokens
        if candidate_tokens > available_for_history_tokens:
            break
        kept_ids.append(turn.turn_id)
        kept_tokens = candidate_tokens
        cursor -= 1
    kept_ids.reverse()
    remaining_ids = tuple(turn.turn_id for turn in turns[:cursor])

    if not remaining_ids:
        outcome: ContextWindowOutcome = "fits_entirely"
    elif kept_ids and compactor is not None:
        outcome = "needs_compaction"
    else:
        outcome = "truncated"

    return ContextWindowDecision(
        kept_turn_ids=tuple(kept_ids),
        turns_to_compact=remaining_ids,
        outcome=outcome,
        available_for_history_tokens=available_for_history_tokens,
        kept_tokens=kept_tokens,
    )


def resolve_num_history_runs(
    decision: ContextWindowDecision,
    *,
    floor: int = 1,
    ceiling: int = 10,
) -> int:
    """Translate a decision into the integer Agno's ``num_history_runs`` expects."""
    return max(floor, min(ceiling, len(decision.kept_turn_ids)))


def estimate_turn_size_tokens(execution_budget: ExecutionBudgetConfig) -> int:
    """Worst-case single-turn size: max reply + a Telegram-size-limit message.

    Not a measured average (no such telemetry exists — content is never
    captured, AGENTS.md §11): a deliberately conservative upper bound built
    only from numbers already governing this run (``max_output_tokens``) or
    enforced by the channel itself (Telegram's hard ``sendMessage`` limit).
    """
    return execution_budget.max_output_tokens + estimate_tokens("x" * MAX_MESSAGE_CHARS)


def resolve_history_ceiling(
    *,
    context_window_tokens: int | None,
    execution_budget: ExecutionBudgetConfig,
    context_budget: ContextBudgetConfig | None,
    floor: int = 1,
    ceiling: int = 10,
) -> int:
    """Approximate how many past turns the run's window can afford, without I/O."""
    available = available_history_tokens(
        context_window_tokens=context_window_tokens,
        execution_budget=execution_budget,
        context_budget=context_budget,
    )
    turn_size = estimate_turn_size_tokens(execution_budget)
    return max(floor, min(ceiling, available // turn_size))
