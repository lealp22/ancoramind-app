"""Pure context-window policy models — no Agno, no I/O (BL-34/specs/030).

Independent of ``src.domain.runtime_config`` by design: runtime_config will
import ``ContextBudgetConfig`` from here (specs/030 T2), so this module must
not import runtime_config back — same split already used between
``src.domain.speech`` and ``src.domain.runtime_config``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

#: Same heuristic already governing cost estimation in
#: ``src.agent.governed_model._messages_char_count`` — kept consistent on
#: purpose rather than introducing a second, incompatible approximation.
_APPROX_CHARS_PER_TOKEN = 4


def estimate_tokens(text: str) -> int:
    """Deterministic, provider-agnostic approximation: ``len(text) // 4``.

    Known limitation (spec.md §8): this is not a real per-provider
    tokenizer and may under/over-estimate depending on language and model.
    """
    return len(text) // _APPROX_CHARS_PER_TOKEN


class ContextPolicyModel(BaseModel):
    """Closed, immutable base — avoids silently accepting unknown fields."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class ContextBudgetConfig(ContextPolicyModel):
    """Reserved slices of the effective window, as absolute token counts."""

    reserved_for_instructions_tokens: int = Field(ge=0)
    reserved_for_current_message_tokens: int = Field(ge=0)
    reserved_for_tools_schema_tokens: int = Field(ge=0)
    safety_margin_tokens: int = Field(ge=0)


@dataclass(frozen=True)
class ConversationTurn:
    """An opaque past turn: identifier + pre-estimated size, never content.

    The policy must never see real conversation text (spec.md §5.2) — the
    caller applies ``estimate_tokens`` to the real turn text and passes only
    the resulting size here.
    """

    turn_id: str
    estimated_tokens: int

    def __post_init__(self) -> None:
        if not self.turn_id:
            raise ValueError("turn_id must not be empty")
        if self.estimated_tokens < 0:
            raise ValueError("estimated_tokens must not be negative")


ContextWindowOutcome = Literal["fits_entirely", "truncated", "needs_compaction"]


@dataclass(frozen=True)
class ContextWindowDecision:
    """Result of selecting how much past history fits the available budget."""

    kept_turn_ids: tuple[str, ...]
    turns_to_compact: tuple[str, ...]
    outcome: ContextWindowOutcome
    available_for_history_tokens: int
    kept_tokens: int
