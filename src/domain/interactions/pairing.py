"""Governed Telegram evaluator pairing domain models (BL-24)."""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class PairingInvitationStatus(StrEnum):
    ACTIVE = "active"
    REVOKED = "revoked"
    EXPIRED = "expired"
    EXHAUSTED = "exhausted"


class PairingRequestStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    REVOKED = "revoked"


class PairingInvitation(BaseModel):
    """Auditable invitation metadata; the redeemable code is never persisted."""

    model_config = ConfigDict(from_attributes=True, frozen=True)

    id: UUID
    status: PairingInvitationStatus
    max_uses: int
    use_count: int
    expires_at: datetime
    created_by: str
    reason: str
    created_at: datetime
    revoked_by: str | None = None
    revoked_reason: str | None = None
    revoked_at: datetime | None = None


class PairingRequest(BaseModel):
    """A private-chat user's pairing request, pending explicit operator approval."""

    model_config = ConfigDict(from_attributes=True, frozen=True)

    id: UUID
    invitation_id: UUID
    telegram_user_id: int
    status: PairingRequestStatus
    requested_at: datetime
    decided_by: str | None = None
    decision_reason: str | None = None
    decided_at: datetime | None = None


class PairingInvitationCreate(BaseModel):
    """Validated operator input for one bounded, temporary invitation."""

    model_config = ConfigDict(frozen=True)

    max_uses: int = Field(default=1, ge=1, le=100)
    expires_in_minutes: int = Field(default=60, ge=5, le=10080)
    reason: str = Field(min_length=1, max_length=2000)

    @field_validator("reason")
    @classmethod
    def normalize_reason(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("reason must not be blank")
        return normalized


class IssuedPairingInvitation(BaseModel):
    """One-time API result. ``code`` must only be shown to the issuing operator."""

    model_config = ConfigDict(frozen=True)

    invitation: PairingInvitation
    code: str = Field(min_length=20, max_length=128)


def generate_pairing_code() -> str:
    """Create a URL-safe, high-entropy redeemable code with no user semantics."""
    return secrets.token_urlsafe(24)


def hash_pairing_code(code: str, pepper: str) -> str:
    """Return a keyed hash; raw invitation codes must never enter PostgreSQL or logs."""
    normalized = code.strip()
    if not normalized:
        raise ValueError("pairing code must not be blank")
    if not pepper:
        raise ValueError("pairing code pepper must not be blank")
    return hmac.new(pepper.encode("utf-8"), normalized.encode("utf-8"), hashlib.sha256).hexdigest()


def invitation_expiry(minutes: int, now: datetime | None = None) -> datetime:
    """Calculate a UTC expiry from bounded operator input."""
    current = now or datetime.now(tz=UTC)
    return current + timedelta(minutes=minutes)
