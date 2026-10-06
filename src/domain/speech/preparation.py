"""Durable preparation metadata. Audio bytes never belong in this ledger."""

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from pydantic import Field

from src.domain.interactions.payloads import TelegramPayloadCipher
from src.domain.speech.models import SpeechModel, SpeechToTextResult


class PreparationStatus(StrEnum):
    PREPARING = "preparing"
    DOWNLOADED = "downloaded"
    TRANSCRIBING = "transcribing"
    TRANSCRIBED = "transcribed"
    FAILED_CONTROLLED = "failed_controlled"
    FAILED_AMBIGUOUS = "failed_ambiguous"


class VoicePreparation(SpeechModel):
    """Opaque persisted result and bounded usage metadata; not consent evidence."""

    interaction_id: UUID
    user_id: int
    owner_token: UUID = Field(repr=False)
    status: PreparationStatus
    config_revision: int
    call_id: UUID | None = None
    logical_route: str | None = None
    effective_route: str | None = None
    duration_seconds: Decimal | None = None
    size_bytes: int | None = None
    estimated_cost: Decimal | None = None
    actual_cost: Decimal | None = None
    transcript_ciphertext: bytes | None = Field(default=None, repr=False)
    transcript_key_version: int | None = None
    transcript_expires_at: datetime | None = None
    claimed_at: datetime
    updated_at: datetime


class SpeechTranscriptCipher:
    """Reuse the channel encryption boundary without retaining raw audio."""

    def __init__(self, cipher: TelegramPayloadCipher):
        self._cipher = cipher

    def encrypt(self, result: SpeechToTextResult) -> tuple[bytes, int]:
        encrypted = self._cipher.encrypt(
            {"kind": "voice_transcript_v1", "result": result.model_dump(mode="json")}
        )
        return encrypted.ciphertext, encrypted.key_version

    def decrypt(self, ciphertext: bytes) -> SpeechToTextResult:
        payload = self._cipher.decrypt(ciphertext)
        if payload.get("kind") != "voice_transcript_v1":
            raise ValueError("invalid speech transcript envelope")
        return SpeechToTextResult.model_validate(payload.get("result"))
