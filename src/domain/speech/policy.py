"""Pure speech limits and exact duration-based billing; no I/O or authorization."""

from __future__ import annotations

from decimal import Decimal, localcontext
from fractions import Fraction
from typing import Annotated, Literal

from pydantic import Field

from src.domain.speech.models import (
    MAX_VOICE_BYTES,
    MAX_VOICE_SECONDS,
    ExactDecimal,
    InspectedVoiceAudio,
    PositiveSeconds,
    SpeechModel,
    ValidatedVoiceAudio,
    VoiceInputOrigin,
    VoiceReference,
    exact_decimal,
)


class SpeechInputError(ValueError):
    """Safe fixed error code, never a filename, transcript or provider message."""

    def __init__(
        self,
        code: Literal[
            "voice_disabled",
            "voice_origin_not_allowed",
            "voice_duration_exceeded",
            "voice_too_large",
            "voice_format_not_allowed",
            "voice_empty_or_invalid",
        ],
    ) -> None:
        self.code = code
        super().__init__(code)


class SpeechInputPolicy(SpeechModel):
    """MVP caps may be tightened but never exceed five minutes / ten MiB.

    Timeout is a required future infrastructure setting, not an invented default
    in this pure policy. Callers must validate declared metadata before download
    and pass output from a real inspector before considering audio validated.
    """

    enabled: bool = Field(default=False, strict=True)
    max_duration_seconds: int = Field(
        default=MAX_VOICE_SECONDS, strict=True, gt=0, le=MAX_VOICE_SECONDS
    )
    max_size_bytes: int = Field(default=MAX_VOICE_BYTES, strict=True, gt=0, le=MAX_VOICE_BYTES)

    def validate_reference(self, reference: VoiceReference, origin: VoiceInputOrigin) -> None:
        if not self.enabled:
            raise SpeechInputError("voice_disabled")
        if origin.source != "telegram_voice" or origin.message_kind != "original":
            raise SpeechInputError("voice_origin_not_allowed")
        if reference.duration_seconds > self.max_duration_seconds:
            raise SpeechInputError("voice_duration_exceeded")
        if reference.size_bytes is not None and reference.size_bytes > self.max_size_bytes:
            raise SpeechInputError("voice_too_large")
        # Declared MIME is not evidence of the downloaded file's actual format.

    def validate_download_size(self, cumulative_bytes: int) -> None:
        """Check after each streaming chunk; this method itself does not download."""
        if not self.enabled:
            raise SpeechInputError("voice_disabled")
        if type(cumulative_bytes) is not int or cumulative_bytes < 0:
            raise SpeechInputError("voice_empty_or_invalid")
        if cumulative_bytes > self.max_size_bytes:
            raise SpeechInputError("voice_too_large")

    def validate_audio(self, audio: InspectedVoiceAudio) -> ValidatedVoiceAudio:
        self.validate_download_size(len(audio.content))
        if audio.duration_seconds > self.max_duration_seconds:
            raise SpeechInputError("voice_duration_exceeded")
        if audio.mime_type != "audio/ogg" or audio.codec != "opus":
            raise SpeechInputError("voice_format_not_allowed")
        # A cheap mismatch guard, never a substitute for physical inspection.
        if not audio.content.startswith(b"OggS"):
            raise SpeechInputError("voice_empty_or_invalid")
        return ValidatedVoiceAudio(
            content=audio.content,
            duration_seconds=audio.duration_seconds,
            mime_type="audio/ogg",
            codec="opus",
        )


class SpeechCostEstimate(SpeechModel):
    """Exact reservation amount; reservation/accounting are outside this policy."""

    billable_seconds: Decimal
    estimated_cost_usd: Decimal


class SpeechBillingPolicy(SpeechModel):
    """Versioned tariff; an explicit zero tariff is valid, a missing one is not."""

    version: str = Field(min_length=1, max_length=127)
    unit: Literal["duration_seconds"] = "duration_seconds"
    rate_usd_per_second: Annotated[ExactDecimal, Field(ge=0, max_digits=18, decimal_places=9)]
    quantum_seconds: PositiveSeconds
    minimum_seconds: Annotated[ExactDecimal, Field(ge=0, max_digits=18, decimal_places=9)]

    def estimate(self, duration_seconds: Decimal | int | str) -> SpeechCostEstimate:
        duration = exact_decimal(duration_seconds)
        if duration <= 0 or duration > MAX_VOICE_SECONDS:
            raise ValueError("duration must be positive and at most 300 seconds")
        # Fraction avoids division rounding an almost-boundary value down.
        ratio = Fraction(duration) / Fraction(self.quantum_seconds)
        quanta = -(-ratio.numerator // ratio.denominator)
        with localcontext() as context:
            context.prec = 64  # Enough for bounded tariff fields and 300 seconds.
            billable = max(self.minimum_seconds, quanta * self.quantum_seconds)
            cost = billable * self.rate_usd_per_second
        return SpeechCostEstimate(billable_seconds=billable, estimated_cost_usd=cost)

    def maximum_estimate(self) -> SpeechCostEstimate:
        """Derived cap, no second manually configured USD budget."""
        return self.estimate(MAX_VOICE_SECONDS)
