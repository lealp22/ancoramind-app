"""DreamPromotionService policy (specs/029 §4.1) — pure, no I/O, no database.

Covers the five scenarios named in specs/029-dream-personal-memory/tasks.md
T4: explicit activates directly, implicit requires two batches, an explicit
correction supersedes an active value, an out-of-enum category is rejected
at the schema boundary, and Dream never touches canonical memory (there is
no canonical repository anywhere in this module's import graph).
"""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.domain.dream.models import (
    CreateCandidate,
    DreamCandidateProposal,
    DreamCandidateSnapshot,
    DreamCandidateStatus,
    DreamCategory,
    DreamSource,
    ReinforceCandidate,
    RejectProposal,
    ResetCandidate,
    SupersedeCandidate,
)
from src.domain.dream.service import DreamPromotionService


def _proposal(**overrides: object) -> DreamCandidateProposal:
    defaults: dict[str, object] = {
        "category": DreamCategory.TONE_LENGTH,
        "key": "response_length",
        "value": "short",
        "confidence": 0.9,
        "source": DreamSource.IMPLICIT,
    }
    defaults.update(overrides)
    return DreamCandidateProposal.model_validate(defaults)


def _snapshot(**overrides: object) -> DreamCandidateSnapshot:
    defaults: dict[str, object] = {
        "id": uuid4(),
        "category": DreamCategory.TONE_LENGTH,
        "key": "response_length",
        "value": "short",
        "status": DreamCandidateStatus.CANDIDATE,
        "evidence_count": 1,
        "confidence": 0.9,
    }
    defaults.update(overrides)
    return DreamCandidateSnapshot.model_validate(defaults)


def test_explicit_signal_activates_directly_with_no_prior_row():
    """An explicit preference needs no repetition to become active."""
    service = DreamPromotionService()
    proposal = _proposal(source=DreamSource.EXPLICIT, value="prefiero respuestas cortas")

    [mutation] = service.decide(existing=[], proposals=[proposal])

    assert isinstance(mutation, CreateCandidate)
    assert mutation.fields.status is DreamCandidateStatus.ACTIVE
    assert mutation.fields.evidence_count == 1


def test_implicit_signal_requires_two_batches_to_activate():
    """First occurrence creates a candidate; a second matching batch promotes it."""
    service = DreamPromotionService()
    proposal = _proposal(source=DreamSource.IMPLICIT)

    [first] = service.decide(existing=[], proposals=[proposal])
    assert isinstance(first, CreateCandidate)
    assert first.fields.status is DreamCandidateStatus.CANDIDATE
    assert first.fields.evidence_count == 1

    pending = _snapshot(status=DreamCandidateStatus.CANDIDATE, evidence_count=1)
    [second] = service.decide(existing=[pending], proposals=[proposal])

    assert isinstance(second, ReinforceCandidate)
    assert second.existing_id == pending.id
    assert second.evidence_count == 2
    assert second.promote_to_active is True


def test_explicit_correction_supersedes_an_active_value():
    """A new explicit value for an already-active key replaces it, not merges."""
    service = DreamPromotionService()
    active = _snapshot(status=DreamCandidateStatus.ACTIVE, value="short", evidence_count=1)
    proposal = _proposal(source=DreamSource.EXPLICIT, value="largo, con detalle")

    [mutation] = service.decide(existing=[active], proposals=[proposal])

    assert isinstance(mutation, SupersedeCandidate)
    assert mutation.existing_id == active.id
    assert mutation.replacement.status is DreamCandidateStatus.ACTIVE
    assert mutation.replacement.value == "largo, con detalle"


def test_category_outside_the_closed_enum_is_rejected_at_the_schema_boundary():
    """An out-of-enum category never reaches the promotion service at all."""
    with pytest.raises(ValidationError):
        _proposal(category="political_opinion")


def test_dream_service_has_no_canonical_memory_dependency():
    """Dream never touches notes/vehicles/reminders/calendar/todos — by import graph."""
    import src.domain.dream.service as module

    forbidden = ("notes", "vehicles", "reminders", "calendar", "todos", "actions")
    assert not any(name in module.__dict__ for name in forbidden)
    assert "src.repositories" not in module.__name__  # pure domain, not a repository


def test_implicit_signal_never_overwrites_an_active_value():
    """Active state wins: a contradicting implicit proposal is rejected, not applied."""
    service = DreamPromotionService()
    active = _snapshot(status=DreamCandidateStatus.ACTIVE, value="short", evidence_count=1)
    proposal = _proposal(source=DreamSource.IMPLICIT, value="largo")

    [mutation] = service.decide(existing=[active], proposals=[proposal])

    assert isinstance(mutation, RejectProposal)
    assert mutation.fields.status is DreamCandidateStatus.REJECTED
    assert mutation.fields.value == "largo"


def test_reinforcing_an_identical_active_value_is_a_no_op():
    service = DreamPromotionService()
    active = _snapshot(status=DreamCandidateStatus.ACTIVE, value="short", evidence_count=1)
    proposal = _proposal(source=DreamSource.IMPLICIT, value="short")

    mutations = service.decide(existing=[active], proposals=[proposal])

    assert mutations == []


def test_contradicting_implicit_signal_resets_the_candidate_counter():
    service = DreamPromotionService()
    pending = _snapshot(status=DreamCandidateStatus.CANDIDATE, value="short", evidence_count=1)
    proposal = _proposal(source=DreamSource.IMPLICIT, value="largo")

    [mutation] = service.decide(existing=[pending], proposals=[proposal])

    assert isinstance(mutation, ResetCandidate)
    assert mutation.existing_id == pending.id
    assert mutation.replacement.value == "largo"
    assert mutation.replacement.evidence_count == 1
    assert mutation.replacement.status is DreamCandidateStatus.CANDIDATE


def test_explicit_signal_overrides_a_pending_implicit_candidate_outright():
    service = DreamPromotionService()
    pending = _snapshot(status=DreamCandidateStatus.CANDIDATE, value="short", evidence_count=1)
    proposal = _proposal(source=DreamSource.EXPLICIT, value="largo, con detalle")

    [mutation] = service.decide(existing=[pending], proposals=[proposal])

    assert isinstance(mutation, SupersedeCandidate)
    assert mutation.existing_id == pending.id
    assert mutation.replacement.status is DreamCandidateStatus.ACTIVE


def test_duplicate_existing_rows_for_the_same_key_are_rejected_defensively():
    service = DreamPromotionService()
    row_a = _snapshot(status=DreamCandidateStatus.CANDIDATE)
    row_b = _snapshot(status=DreamCandidateStatus.ACTIVE)

    with pytest.raises(ValueError, match="duplicate"):
        service.decide(existing=[row_a, row_b], proposals=[])


def test_duplicate_proposals_for_the_same_key_in_one_batch_are_rejected():
    service = DreamPromotionService()
    proposal = _proposal()

    with pytest.raises(ValueError, match="duplicate"):
        service.decide(existing=[], proposals=[proposal, proposal])
