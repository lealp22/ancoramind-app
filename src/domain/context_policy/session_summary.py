"""Session-exchange summarization — BL-34 (2026-10-12), a different path
from ``compaction.py``'s original ``ConversationTurn``/opaque-turn-id
design.

That design assumed reading Agno's real session turns (specs/030 §6
explicitly deferred that I/O). This path never touches ``agno_runtime``:
it summarizes AncoraMind's own governed exchange ledger (the user's message
+ the Agent's final reply per interaction, already decrypted by the
caller) — domain-owned data, no coupling to Agno's internal schema.
``CompactionPort``/``CompactionOutcome`` in ``compaction.py`` stay as
written, still inert, for the turn-based design they were meant for.

Pure, no Agno import. The physical adapter lives in ``src/agent/``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class SessionExchange:
    """One decrypted user/assistant exchange from the interaction ledger.

    Either side may be ``None`` (e.g. a bot command, or a final reply that
    was never persisted) — the caller skips exchanges with nothing to say.
    """

    interaction_id: str
    user_text: str | None
    assistant_text: str | None


@dataclass(frozen=True)
class SessionSummaryOutcome:
    """Controlled result of one summarization attempt. Never raises."""

    summary_text: str | None
    status: str
    error_class: str | None = None


class SessionSummarizationPort(Protocol):
    """Inference boundary an adapter must resolve through ``LLMAccess``.

    A failed or over-budget summary degrades to ``status="failed"``
    instead of raising — the caller must never let a compaction failure
    abort the run it was trying to improve.
    """

    async def summarize(self, exchanges: tuple[SessionExchange, ...]) -> SessionSummaryOutcome: ...


__all__ = ["SessionExchange", "SessionSummarizationPort", "SessionSummaryOutcome"]
