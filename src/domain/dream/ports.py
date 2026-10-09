"""Domain-owned ports for Dream (specs/029 T3). Physical adapters live in
``src/agent/`` (consolidation, through LLMAccess) and ``src/repositories/``
(persistence, T1/T2 — not implemented yet; this module only defines the
shape ``DreamWorker`` depends on, so the worker is testable without a real
repository or database).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from src.domain.dream.models import (
    DreamCandidateSnapshot,
    DreamConsolidationOutcome,
    DreamMutation,
)


@dataclass(frozen=True)
class DreamBatch:
    """One user's eligible unconsumed transcripts plus their current candidates.

    ``transcripts`` are already decrypted, truncated plaintext (DATA, not
    instructions) — the repository owns decryption; this port never sees
    ciphertext. ``cursor_interaction_id`` is the last transcript's
    ``interaction_id``, advanced only after the batch is applied.
    """

    user_id: str
    transcripts: tuple[str, ...]
    existing: tuple[DreamCandidateSnapshot, ...]
    cursor_interaction_id: UUID


class DreamConsolidationPort(Protocol):
    """Governed LLM boundary — the only place Dream may produce inference.

    Implementations must resolve through ``LLMAccess`` with a snapshot,
    budget and trace, and must never place transcript content in error
    metadata (specs/029 §5).
    """

    async def consolidate(self, batch: DreamBatch) -> DreamConsolidationOutcome: ...


class DreamRepositoryPort(Protocol):
    """Persistence boundary for the worker — concrete SQL lands in T1/T2.

    ``claim_eligible_batches`` is responsible for the batch-size/cadence
    threshold (specs/029 §7); a user with too few unconsumed transcripts and
    too little elapsed time since their last batch is simply not returned.
    """

    async def claim_eligible_batches(self, *, limit: int) -> list[DreamBatch]: ...

    async def apply_batch_result(
        self,
        user_id: str,
        *,
        mutations: Sequence[DreamMutation],
        cursor_interaction_id: UUID,
        outcome: DreamConsolidationOutcome,
    ) -> None: ...

    async def record_run_failure(
        self, user_id: str, outcome: DreamConsolidationOutcome
    ) -> None: ...

    async def purge_expired(self) -> int: ...


__all__ = ["DreamBatch", "DreamConsolidationPort", "DreamRepositoryPort"]
