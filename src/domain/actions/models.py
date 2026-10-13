"""Governed-mutation consent model (specs/023 T4, specs/022 consent-design.md).

Pure domain types: no Agno, Telegram SDK or SQL. The repository enforces the
state machine atomically; these types name its states and rejection reasons
so callers never branch on raw strings.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any
from uuid import UUID

CONSENT_TTL = timedelta(minutes=15)
"""A proposal is confirmable for 15 minutes after its verified delivery."""


class ProposalStatus(StrEnum):
    PENDING_CONFIRMATION = "pending_confirmation"
    CONFIRMED = "confirmed"
    EXECUTING = "executing"
    EXECUTED = "executed"
    FAILED_DEFINITIVE = "failed_definitive"
    FAILED_AMBIGUOUS = "failed_ambiguous"
    EXPIRED = "expired"
    DISCARDED = "discarded"


class ConsentMode(StrEnum):
    """How a proposal's execution was authorised (specs/035, BL-46).

    Orthogonal to ``ProposalStatus``: it records the authorisation path, not
    the state machine position. ``explicit_confirmation`` is the existing
    WRITE_REVIEWABLE path (a user "Sí" claimed via ``claim_confirmation``
    before ``ProposalExecutor`` ran it); ``self_authorized`` is the
    WRITE_TRIVIAL path (``TrivialExecutor``), where the row is inserted
    directly in a terminal ``executed`` state because the user's own request
    already was the signal (same precedent as ``analyze_document``).
    """

    EXPLICIT_CONFIRMATION = "explicit_confirmation"
    SELF_AUTHORIZED = "self_authorized"


class ConsentRejection(StrEnum):
    """Why a confirmation claim did not consume a proposal (content-free)."""

    NOT_FOUND = "not_found"
    """No proposal with that id for this principal (or another user's)."""
    LEGACY_PROPOSAL = "legacy_proposal"
    """Created before consent evidence existed: no provenance/payload hash."""
    NOT_PRESENTED = "not_presented"
    """The proposal was never delivered to the user in a verified response."""
    EXPIRED = "expired"
    NOT_PENDING = "not_pending"
    """Already confirmed, consumed, failed, expired or discarded."""
    PRINCIPAL_MISMATCH = "principal_mismatch"
    """Different bot or chat than the one the proposal was presented in."""
    PAYLOAD_TAMPERED = "payload_tampered"
    """Stored payload no longer matches the hash recorded at creation."""
    INTERACTION_ALREADY_USED = "interaction_already_used"
    """That confirming interaction already authorised another proposal."""


@dataclass(frozen=True)
class ConsentPrincipal:
    """Trusted identity of whoever confirms, resolved by the channel adapter."""

    user_id: str
    bot_id: int
    chat_id: int


@dataclass(frozen=True)
class ClaimedProposal:
    """A proposal whose consent was atomically consumed; safe to execute once."""

    id: UUID
    tool_name: str
    payload: dict[str, Any]
    source_document_id: UUID | None
    confirming_interaction_id: UUID


@dataclass(frozen=True)
class ConsentClaimResult:
    claimed: ClaimedProposal | None = None
    rejection: ConsentRejection | None = None

    @property
    def ok(self) -> bool:
        return self.claimed is not None


def payload_hash(tool_name: str, payload: dict[str, Any]) -> str:
    """Canonical SHA-256 of (tool, payload); detects tampering after creation.

    ``sort_keys`` + compact separators make the hash independent of key order
    and of the JSONB round-trip. ``default=str`` mirrors how payloads are
    serialised when stored.
    """
    canonical = json.dumps(
        {"tool_name": tool_name, "payload": payload},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def consent_deadline(presented_at: datetime) -> datetime:
    """Expiry computed from verified delivery, never from creation time."""
    return presented_at + CONSENT_TTL
