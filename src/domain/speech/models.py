"""Immutable speech contracts; none of these models authenticates its own origin."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, field_validator

MAX_VOICE_SECONDS = 300
MAX_VOICE_BYTES = 10 * 1024 * 1024
MAX_TRANSCRIPT_CHARS = 16000


def exact_decimal(value: object) -> Decimal:
    """Reject binary floats, booleans and non-finite numbers at the boundary."""
    if isinstance(value, bool) or not isinstance(value, (Decimal, int, str)):
        raise ValueError("an exact decimal value is required")
    try:
        result = Decimal(value)
    except ArithmeticError as exc:
        raise ValueError("an exact decimal value is required") from exc
    if not result.is_finite():
        raise ValueError("a finite decimal value is required")
    return result


ExactDecimal = Annotated[Decimal, BeforeValidator(exact_decimal)]
PositiveSeconds = Annotated[ExactDecimal, Field(gt=0, max_digits=18, decimal_places=9)]


class SpeechModel(BaseModel):
    """Avoid accidental repr leakage and validation errors echoing personal data."""

    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)


class VoiceInputOrigin(SpeechModel):
    """Metadata supplied by the admitted channel, never by STT or a model."""

    interaction_id: UUID
    bot_id: int = Field(strict=True, gt=0)
    chat_id: int = Field(strict=True)
    user_id: str = Field(min_length=1, max_length=255, repr=False)
    accepted_at: datetime
    message_id: int = Field(strict=True, gt=0)
    conversation_generation: int = Field(strict=True, ge=0)
    source: Literal["telegram_voice", "document", "history", "tool_result"]
    message_kind: Literal["original", "forwarded", "edited", "mixed"]

    @field_validator("accepted_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("accepted_at must include a timezone")
        return value


class VoiceReference(SpeechModel):
    """Untrusted declared metadata, separate from the production Telegram adapter."""

    file_id: str = Field(min_length=1, max_length=255, strict=True, repr=False)
    duration_seconds: int = Field(strict=True, gt=0)
    size_bytes: int | None = Field(default=None, strict=True, ge=0)
    mime_type: str | None = Field(default=None, max_length=127, strict=True)

    @field_validator("file_id")
    @classmethod
    def require_nonblank_id(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("file_id must not be blank")
        return value


class InspectedVoiceAudio(SpeechModel):
    """Trusted adapter output after inspecting these bytes, NOT a decoder itself.

    Only the future inspection adapter may produce this contract for runtime.
    Construction of a model does not prove that its content is valid audio.
    """

    content: bytes = Field(strict=True, repr=False, min_length=1, max_length=MAX_VOICE_BYTES)
    mime_type: str = Field(min_length=1, max_length=127)
    codec: str = Field(min_length=1, max_length=63)
    duration_seconds: PositiveSeconds


class ValidatedVoiceAudio(InspectedVoiceAudio):
    """Inspected OGG/Opus satisfying the absolute MVP limits."""

    mime_type: Literal["audio/ogg"] = "audio/ogg"
    codec: Literal["opus"] = "opus"
    duration_seconds: Annotated[PositiveSeconds, Field(le=MAX_VOICE_SECONDS)]


class SpeechToTextResult(SpeechModel):
    """Untrusted transcript and usage references, without permission fields."""

    text: str = Field(strict=True, min_length=1, max_length=MAX_TRANSCRIPT_CHARS, repr=False)
    duration_seconds: Annotated[PositiveSeconds, Field(le=MAX_VOICE_SECONDS)]
    call_id: UUID
    usage_event_id: UUID
    language: str | None = Field(default=None, min_length=1, max_length=31)

    @field_validator("text")
    @classmethod
    def reject_blank_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("transcript must contain non-whitespace text")
        return value  # Do not trim/truncate into a confirmation phrase.
