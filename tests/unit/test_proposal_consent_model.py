"""Unit tests for the consent domain model (specs/023 T4.1-T4.2).

The state machine itself is covered against PostgreSQL in
``tests/integration/test_proposal_consent.py``; these tests pin the pure parts
(hashing and rejection ordering) so they run without Docker.
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

from src.domain.actions.models import (
    CONSENT_TTL,
    ConsentPrincipal,
    ConsentRejection,
    consent_deadline,
    payload_hash,
)
from src.repositories.actions import ActionProposalsRepository

PRINCIPAL = ConsentPrincipal(user_id="42", bot_id=1, chat_id=2)


def _row(**overrides: object) -> SimpleNamespace:
    payload = {"title": "ITV"}
    values: dict[str, object] = {
        "tool_name": "create_reminder",
        "payload": payload,
        "payload_hash": payload_hash("create_reminder", payload),
        "source_interaction_id": uuid4(),
        "bot_id": 1,
        "chat_id": 2,
        "status": "pending_confirmation",
        "presented_at": datetime.now(tz=UTC),
        "is_expired": False,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_payload_hash_is_order_independent_and_tool_bound() -> None:
    assert payload_hash("t", {"a": 1, "b": 2}) == payload_hash("t", {"b": 2, "a": 1})
    assert payload_hash("t", {"a": 1}) != payload_hash("other", {"a": 1})
    assert payload_hash("t", {"a": 1}) != payload_hash("t", {"a": 2})


def test_consent_deadline_counts_from_delivery() -> None:
    presented = datetime(2026, 10, 2, 17, 0, tzinfo=UTC)
    assert consent_deadline(presented) - presented == CONSENT_TTL


def test_valid_row_is_claimable() -> None:
    assert ActionProposalsRepository._claim_rejection(_row(), PRINCIPAL) is None


def test_rejection_reasons() -> None:
    check = ActionProposalsRepository._claim_rejection
    assert check(None, PRINCIPAL) is ConsentRejection.NOT_FOUND
    assert check(_row(payload_hash=None), PRINCIPAL) is ConsentRejection.LEGACY_PROPOSAL
    assert check(_row(source_interaction_id=None), PRINCIPAL) is ConsentRejection.LEGACY_PROPOSAL
    assert check(_row(chat_id=99), PRINCIPAL) is ConsentRejection.PRINCIPAL_MISMATCH
    assert check(_row(status="confirmed"), PRINCIPAL) is ConsentRejection.NOT_PENDING
    assert check(_row(presented_at=None), PRINCIPAL) is ConsentRejection.NOT_PRESENTED
    assert check(_row(is_expired=True), PRINCIPAL) is ConsentRejection.EXPIRED
    assert (
        check(_row(payload={"title": "cambiado"}), PRINCIPAL)
        is ConsentRejection.PAYLOAD_TAMPERED
    )


def test_legacy_beats_every_other_reason() -> None:
    """A legacy row is never executable, whatever else is wrong with it."""
    row = _row(payload_hash=None, chat_id=99, presented_at=None, is_expired=True)
    assert (
        ActionProposalsRepository._claim_rejection(row, PRINCIPAL)
        is ConsentRejection.LEGACY_PROPOSAL
    )
