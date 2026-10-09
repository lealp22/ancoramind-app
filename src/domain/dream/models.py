"""Dream domain models (specs/029 §3.2-3.3, §4). Pure Pydantic, no I/O.

The category enum is closed by design: anything outside it is a validation
error at construction time, never a value persisted "just in case" (specs/029
§3.3 — sensitive/third-party/secret data must never reach this far).
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class DreamCategory(StrEnum):
    """Closed set approved in specs/029 §3.3. Extending this is a spec change."""

    LANGUAGE = "language"
    TONE_LENGTH = "tone_length"
    NICKNAME = "nickname"
    FORMATTING_PREFERENCE = "formatting_preference"
    RECURRING_HABIT = "recurring_habit"
    INTERACTION_SCHEDULE = "interaction_schedule"


class DreamCandidateStatus(StrEnum):
    CANDIDATE = "candidate"
    ACTIVE = "active"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"
    DELETED = "deleted"


class DreamSource(StrEnum):
    EXPLICIT = "explicit"
    IMPLICIT = "implicit"


# Batches required for an implicit pattern to earn `active`, absent any
# contradicting signal in between (specs/029 §4.1).
IMPLICIT_PROMOTION_THRESHOLD = 2


class DreamModel(BaseModel):
    """Avoid accidental repr leakage; mirrors SpeechModel's defensive posture."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class DreamCandidateSnapshot(DreamModel):
    """Read-only view of one existing `active` or `candidate` row for a user.

    The caller (worker/repository layer) is responsible for only passing in
    rows that are still `active` or `candidate` — this service never needs to
    see `rejected`/`superseded`/`deleted` history to decide the next mutation.
    """

    id: UUID
    category: DreamCategory
    key: str = Field(min_length=1, max_length=63)
    value: str = Field(min_length=1, max_length=500)
    status: Literal[DreamCandidateStatus.ACTIVE, DreamCandidateStatus.CANDIDATE]
    evidence_count: int = Field(ge=1)
    confidence: float = Field(ge=0.0, le=1.0)


class DreamCandidateProposal(DreamModel):
    """One preference signal proposed by the governed LLM for one batch.

    Untrusted provenance (model output), but schema-validated: an invalid
    category can never reach the promotion service at all.
    """

    category: DreamCategory
    key: str = Field(min_length=1, max_length=63)
    value: str = Field(min_length=1, max_length=500)
    confidence: float = Field(ge=0.0, le=1.0)
    source: DreamSource


class DreamCandidateFields(DreamModel):
    """The row contents for a brand-new `dream_candidates` insert."""

    category: DreamCategory
    key: str
    value: str
    confidence: float
    status: DreamCandidateStatus
    source: DreamSource
    evidence_count: int = Field(ge=1)


class CreateCandidate(DreamModel):
    """Insert one new row with no prior match for this (category, key)."""

    op: Literal["create"] = "create"
    fields: DreamCandidateFields


class SupersedeCandidate(DreamModel):
    """Mark an existing `active` row superseded and insert its replacement.

    Only an explicit signal may trigger this (specs/029 §4.1): an implicit
    proposal never overwrites an active value, it is rejected instead (see
    `RejectProposal`).
    """

    op: Literal["supersede"] = "supersede"
    existing_id: UUID
    replacement: DreamCandidateFields


class ReinforceCandidate(DreamModel):
    """Bump evidence on a matching `candidate` row; promote at the threshold."""

    op: Literal["reinforce"] = "reinforce"
    existing_id: UUID
    evidence_count: int = Field(ge=1)
    promote_to_active: bool


class ResetCandidate(DreamModel):
    """A contradicting implicit signal arrived before the candidate was
    promoted: the old row is rejected and counting restarts from one.
    """

    op: Literal["reset"] = "reset"
    existing_id: UUID
    replacement: DreamCandidateFields


class RejectProposal(DreamModel):
    """An implicit signal contradicts an existing `active` value.

    Recorded as its own `rejected` row for audit, without touching the
    active value it conflicted with — canonical/active state always wins.
    """

    op: Literal["reject"] = "reject"
    fields: DreamCandidateFields


DreamMutation = (
    CreateCandidate | SupersedeCandidate | ReinforceCandidate | ResetCandidate | RejectProposal
)

__all__ = [
    "IMPLICIT_PROMOTION_THRESHOLD",
    "CreateCandidate",
    "DreamCandidateFields",
    "DreamCandidateProposal",
    "DreamCandidateSnapshot",
    "DreamCandidateStatus",
    "DreamCategory",
    "DreamModel",
    "DreamMutation",
    "DreamSource",
    "RejectProposal",
    "ReinforceCandidate",
    "ResetCandidate",
    "SupersedeCandidate",
]
