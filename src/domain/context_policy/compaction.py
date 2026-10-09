"""CompactionPort — deferred contract for real history compaction (BL-34/specs/030 T5).

Only the interface is defined in this increment. No physical implementation
exists yet, no logical route is wired to `LLMAccess` for it, and
`select_history_window` never calls it: when `outcome="needs_compaction"` and
no `CompactionPort` is configured (the only case today), the policy degrades
to `outcome="truncated"` instead (spec.md §7). Activating a real compactor is
explicit future work, not something this module enables by its mere
existence.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class CompactionOutcome:
    """Controlled result of one compaction attempt.

    ``summary_text`` is a synthesized checkpoint, never persisted as personal
    or canonical memory (spec.md §7) — it lives only for the remaining
    lifetime of the conversational session, exactly like Agno's own history.
    ``error_class``/``error_detail`` carry bounded operational metadata only,
    never document content or prompts (same discipline as
    ``DocumentExtractionOutcome``).
    """

    summary_text: str | None
    compacted_from_turn_id: str
    compacted_to_turn_id: str
    status: str
    error_class: str | None = None
    error_detail: str | None = None


class CompactionPort(Protocol):
    """Inference boundary a future increment would own, analogous to
    ``DocumentExtractionPort`` (specs/013 T9).

    An implementation must resolve its model through ``LLMAccess`` (fail
    closed, never a direct provider call) and must surface failures as a
    controlled ``CompactionOutcome`` instead of raising — a failed or
    over-budget compaction degrades to ``outcome="truncated"`` with no
    retries, same principle as ``retries=0`` everywhere else in this repo.
    """

    async def compact(
        self,
        turn_ids: tuple[str, ...],
        *,
        compacted_from_turn_id: str,
        compacted_to_turn_id: str,
    ) -> CompactionOutcome: ...
