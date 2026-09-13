"""Application-level encryption and retention rules for Telegram payloads."""

from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

from src.domain.interactions.models import InteractionStatus


class PayloadEncryptionUnavailableError(RuntimeError):
    """Raised when a recoverable payload is requested without an application key."""


@dataclass(frozen=True)
class EncryptedPayload:
    """Opaque encrypted payload and safe metadata for the ledger."""

    ciphertext: bytes
    key_version: int
    fingerprint: str


class TelegramPayloadCipher:
    """Encrypt normalized Telegram data and create non-reversible fingerprints."""

    def __init__(self, key: str, key_version: int, fingerprint_key: str | None = None):
        if not key:
            raise PayloadEncryptionUnavailableError(
                "TELEGRAM_PAYLOAD_ENCRYPTION_KEY is required to persist recoverable payloads"
            )
        try:
            self._fernet = Fernet(key.encode("ascii"))
        except (TypeError, ValueError) as exc:
            raise ValueError("TELEGRAM_PAYLOAD_ENCRYPTION_KEY is not a valid Fernet key") from exc
        self._key_version = key_version
        self._fingerprint_key = (fingerprint_key or key).encode("utf-8")

    def encrypt(self, payload: dict[str, Any]) -> EncryptedPayload:
        """Serialize deterministically, encrypt, and return an HMAC fingerprint."""
        plaintext = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return EncryptedPayload(
            ciphertext=self._fernet.encrypt(plaintext),
            key_version=self._key_version,
            fingerprint=hmac.new(self._fingerprint_key, plaintext, hashlib.sha256).hexdigest(),
        )

    def decrypt(self, ciphertext: bytes) -> dict[str, Any]:
        """Decrypt a payload for controlled in-process recovery only."""
        try:
            decoded = self._fernet.decrypt(ciphertext)
            payload = json.loads(decoded)
        except (InvalidToken, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError(
                "Telegram payload cannot be decrypted with the configured key"
            ) from exc
        if not isinstance(payload, dict):
            raise ValueError("Telegram payload must decode to an object")
        return payload


def payload_expiry_for(status: InteractionStatus, now: datetime | None = None) -> datetime | None:
    """Return the initial retention deadline; non-terminal payloads remain recoverable."""
    current = now or datetime.now(tz=UTC)
    if status in {
        InteractionStatus.COMPLETED,
        InteractionStatus.IGNORED,
        InteractionStatus.REJECTED,
    }:
        return current + timedelta(hours=24)
    if status is InteractionStatus.FAILED_AMBIGUOUS:
        return current + timedelta(days=7)
    if status in {
        InteractionStatus.FAILED_CONTROLLED,
        InteractionStatus.FAILED_DEFINITIVE,
    }:
        return current + timedelta(hours=24)
    return None
