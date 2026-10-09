"""DreamPromotionService — pure promotion policy (specs/029 §4.1).

No I/O: the worker (T3) reads existing `active`/`candidate` rows and the
LLM's proposals, calls `decide()`, and applies the returned mutations in one
transaction. Keeping this pure makes the five promotion scenarios (explicit
activates directly, implicit needs two batches, explicit corrections
supersede, contradicting implicit signals are rejected or reset counting,
reinforcement of an already-active value is a no-op) fully unit-testable
without a repository or a database.
"""

from __future__ import annotations

from src.domain.dream.models import (
    IMPLICIT_PROMOTION_THRESHOLD,
    CreateCandidate,
    DreamCandidateFields,
    DreamCandidateProposal,
    DreamCandidateSnapshot,
    DreamCandidateStatus,
    DreamMutation,
    DreamSource,
    ReinforceCandidate,
    RejectProposal,
    ResetCandidate,
    SupersedeCandidate,
)


class DreamPromotionService:
    """Stateless; every call is independent, scoped to one user's batch."""

    def decide(
        self,
        existing: list[DreamCandidateSnapshot],
        proposals: list[DreamCandidateProposal],
    ) -> list[DreamMutation]:
        """Return the mutations to apply for one batch of proposals.

        ``existing`` must contain at most one row per ``(category, key)`` —
        the invariant the unique-active index plus "one candidate in flight
        per key" is expected to guarantee upstream. Two proposals sharing a
        ``(category, key)`` in the same batch are likewise rejected: the
        governed LLM call is expected to produce at most one signal per key
        per batch, and silently picking a winner would hide a contract
        violation instead of surfacing it.
        """
        by_key: dict[tuple[str, str], DreamCandidateSnapshot] = {}
        for row in existing:
            index = (row.category.value, row.key)
            if index in by_key:
                raise ValueError("duplicate active/candidate row for the same (category, key)")
            by_key[index] = row

        seen_this_batch: set[tuple[str, str]] = set()
        mutations: list[DreamMutation] = []
        for proposal in proposals:
            index = (proposal.category.value, proposal.key)
            if index in seen_this_batch:
                raise ValueError("duplicate proposal for the same (category, key) in one batch")
            seen_this_batch.add(index)
            mutation = self._decide_one(by_key.get(index), proposal)
            if mutation is not None:
                mutations.append(mutation)
        return mutations

    def _decide_one(
        self,
        existing_row: DreamCandidateSnapshot | None,
        proposal: DreamCandidateProposal,
    ) -> DreamMutation | None:
        if existing_row is None:
            return CreateCandidate(fields=self._new_fields(proposal, evidence_count=1))

        same_value = existing_row.value == proposal.value

        if existing_row.status is DreamCandidateStatus.ACTIVE:
            if same_value:
                return None  # reinforcing an already-active value needs no write
            if proposal.source is DreamSource.EXPLICIT:
                return SupersedeCandidate(
                    existing_id=existing_row.id,
                    replacement=self._new_fields(
                        proposal, status=DreamCandidateStatus.ACTIVE, evidence_count=1
                    ),
                )
            # Implicit never overwrites an active value; active state wins.
            return RejectProposal(
                fields=self._new_fields(
                    proposal, status=DreamCandidateStatus.REJECTED, evidence_count=1
                )
            )

        # existing_row.status is CANDIDATE
        if proposal.source is DreamSource.EXPLICIT:
            # Explicit always wins outright, regardless of the pending value.
            return SupersedeCandidate(
                existing_id=existing_row.id,
                replacement=self._new_fields(
                    proposal, status=DreamCandidateStatus.ACTIVE, evidence_count=1
                ),
            )
        if same_value:
            evidence_count = existing_row.evidence_count + 1
            return ReinforceCandidate(
                existing_id=existing_row.id,
                evidence_count=evidence_count,
                promote_to_active=evidence_count >= IMPLICIT_PROMOTION_THRESHOLD,
            )
        # A contradicting implicit signal before promotion restarts counting.
        return ResetCandidate(
            existing_id=existing_row.id,
            replacement=self._new_fields(
                proposal, status=DreamCandidateStatus.CANDIDATE, evidence_count=1
            ),
        )

    @staticmethod
    def _new_fields(
        proposal: DreamCandidateProposal,
        *,
        evidence_count: int,
        status: DreamCandidateStatus | None = None,
    ) -> DreamCandidateFields:
        resolved_status = status or (
            DreamCandidateStatus.ACTIVE
            if proposal.source is DreamSource.EXPLICIT
            else DreamCandidateStatus.CANDIDATE
        )
        return DreamCandidateFields(
            category=proposal.category,
            key=proposal.key,
            value=proposal.value,
            confidence=proposal.confidence,
            status=resolved_status,
            source=proposal.source,
            evidence_count=evidence_count,
        )


__all__ = ["DreamPromotionService"]
