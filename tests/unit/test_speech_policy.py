"""Pure T2 acceptance boundaries; synthetic bytes are NOT decoded audio fixtures."""

from datetime import UTC, datetime
from decimal import Decimal, localcontext
from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.domain.speech.models import (
    MAX_TRANSCRIPT_CHARS,
    MAX_VOICE_BYTES,
    InspectedVoiceAudio,
    SpeechToTextResult,
    ValidatedVoiceAudio,
    VoiceInputOrigin,
    VoiceReference,
)
from src.domain.speech.policy import SpeechBillingPolicy, SpeechInputError, SpeechInputPolicy


def origin(**changes):
    return VoiceInputOrigin.model_validate(
        {
            "interaction_id": uuid4(),
            "bot_id": 1,
            "chat_id": 2,
            "user_id": "private-user",
            "accepted_at": datetime.now(UTC),
            "message_id": 3,
            "conversation_generation": 0,
            "source": "telegram_voice",
            "message_kind": "original",
            **changes,
        }
    )


def inspected(**changes):
    return InspectedVoiceAudio.model_validate(
        {
            "content": b"OggSsynthetic-not-decoded",
            "duration_seconds": "300",
            "mime_type": "audio/ogg",
            "codec": "opus",
            **changes,
        }
    )


def tariff(**changes):
    return SpeechBillingPolicy.model_validate(
        {
            "version": "synthetic-r1",
            "rate_usd_per_second": "0.01",
            "quantum_seconds": "60",
            "minimum_seconds": "60",
            **changes,
        }
    )


def test_v03_inclusive_duration_and_size_boundaries():
    policy = SpeechInputPolicy(enabled=True)
    reference = VoiceReference(file_id="safe-id", duration_seconds=300, size_bytes=MAX_VOICE_BYTES)
    policy.validate_reference(reference, origin())
    policy.validate_download_size(MAX_VOICE_BYTES)
    audio = inspected(content=b"OggS" + b"x" * (MAX_VOICE_BYTES - 4))
    assert policy.validate_audio(audio).duration_seconds == Decimal(300)
    with pytest.raises(SpeechInputError, match="voice_duration_exceeded"):
        policy.validate_reference(VoiceReference(file_id="id", duration_seconds=301), origin())
    with pytest.raises(SpeechInputError, match="voice_duration_exceeded"):
        policy.validate_audio(inspected(duration_seconds="300.000000001"))


@pytest.mark.parametrize("value", [0, -1, None, True, False, 1.5, "1", float("inf")])
def test_v04_invalid_declared_duration(value):
    with pytest.raises(ValidationError):
        VoiceReference.model_validate({"file_id": "id", "duration_seconds": value})


@pytest.mark.parametrize("value", ["", " ", "x" * 256, None, 1])
def test_v04_invalid_file_id(value):
    with pytest.raises(ValidationError):
        VoiceReference.model_validate({"file_id": value, "duration_seconds": 1})


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-Infinity", "0", "-1", True, 1.1])
def test_nonfinite_or_inexact_real_duration(value):
    with pytest.raises(ValidationError):
        inspected(duration_seconds=value)


def test_v05_declared_and_streaming_size_rejection():
    policy = SpeechInputPolicy(enabled=True)
    with pytest.raises(SpeechInputError, match="voice_too_large"):
        policy.validate_reference(
            VoiceReference(file_id="id", duration_seconds=1, size_bytes=MAX_VOICE_BYTES + 1),
            origin(),
        )
    with pytest.raises(SpeechInputError, match="voice_too_large"):
        policy.validate_download_size(MAX_VOICE_BYTES + 1)
    with pytest.raises(ValidationError):
        inspected(content=b"x" * (MAX_VOICE_BYTES + 1))


@pytest.mark.parametrize("value", [True, -1, 1.5])
def test_invalid_download_counter(value):
    with pytest.raises(SpeechInputError, match="voice_empty_or_invalid"):
        SpeechInputPolicy(enabled=True).validate_download_size(value)


@pytest.mark.parametrize(
    "changes,code",
    [
        ({"codec": "vorbis"}, "voice_format_not_allowed"),
        ({"mime_type": "application/pdf"}, "voice_format_not_allowed"),
        ({"content": b"%PDF-1.4"}, "voice_empty_or_invalid"),
    ],
)
def test_v06_inspection_format_and_header_mismatch(changes, code):
    with pytest.raises(SpeechInputError, match=code):
        SpeechInputPolicy(enabled=True).validate_audio(inspected(**changes))


def test_v07_optional_metadata_does_not_replace_inspection():
    policy = SpeechInputPolicy(enabled=True)
    policy.validate_reference(VoiceReference(file_id="id", duration_seconds=300), origin())
    assert isinstance(policy.validate_audio(inspected()), ValidatedVoiceAudio)


@pytest.mark.parametrize("text", ["", " \n\t", "x" * (MAX_TRANSCRIPT_CHARS + 1)])
def test_v08_invalid_transcript_is_not_trimmed_into_consent(text):
    with pytest.raises(ValidationError):
        SpeechToTextResult(text=text, duration_seconds="1", call_id=uuid4(), usage_event_id=uuid4())


def test_v08_empty_bytes_rejected():
    with pytest.raises(ValidationError):
        inspected(content=b"")


@pytest.mark.parametrize(
    "changes",
    [
        {"source": "document"},
        {"source": "history"},
        {"source": "tool_result"},
        {"message_kind": "forwarded"},
        {"message_kind": "edited"},
        {"message_kind": "mixed"},
    ],
)
def test_nonoriginal_voice_origin_is_not_eligible(changes):
    with pytest.raises(SpeechInputError, match="voice_origin_not_allowed"):
        SpeechInputPolicy(enabled=True).validate_reference(
            VoiceReference(file_id="id", duration_seconds=1), origin(**changes)
        )


def test_disabled_by_default_and_caps_can_only_be_tightened():
    with pytest.raises(SpeechInputError, match="voice_disabled"):
        SpeechInputPolicy().validate_reference(
            VoiceReference(file_id="id", duration_seconds=1), origin()
        )
    with pytest.raises(ValidationError):
        SpeechInputPolicy(max_duration_seconds=301)
    with pytest.raises(SpeechInputError, match="voice_too_large"):
        SpeechInputPolicy(enabled=True, max_size_bytes=4).validate_audio(inspected())


def test_v11_v12_rounding_minimum_and_derived_cap():
    policy = tariff()
    assert policy.estimate(61).estimated_cost_usd == Decimal("1.20")
    assert policy.estimate(60).billable_seconds == Decimal(60)
    assert policy.estimate("60.000000001").billable_seconds == Decimal(120)
    assert policy.estimate("0.1").billable_seconds == Decimal(60)
    assert policy.maximum_estimate().estimated_cost_usd == Decimal("3.00")
    assert tariff(minimum_seconds="61").estimate(1).billable_seconds == Decimal(61)


def test_decimal_cost_does_not_depend_on_ambient_precision():
    with localcontext() as context:
        context.prec = 2
        assert tariff(rate_usd_per_second="0.123456789").estimate(61).estimated_cost_usd == (
            Decimal("14.814814680")
        )


@pytest.mark.parametrize(
    "changes",
    [
        {"rate_usd_per_second": "-1"},
        {"rate_usd_per_second": "NaN"},
        {"rate_usd_per_second": "Infinity"},
        {"rate_usd_per_second": True},
        {"rate_usd_per_second": 0.01},
        {"quantum_seconds": "0"},
        {"quantum_seconds": "-1"},
        {"minimum_seconds": "-1"},
        {"minimum_seconds": "Infinity"},
        {"unit": "tokens"},
    ],
)
def test_v13_invalid_tariff(changes):
    with pytest.raises(ValidationError):
        tariff(**changes)


def test_v13_missing_tariff_fails_and_explicit_zero_is_valid():
    with pytest.raises(ValidationError):
        SpeechBillingPolicy(version="r1", quantum_seconds="1", minimum_seconds="0")
    assert tariff(rate_usd_per_second="0").maximum_estimate().estimated_cost_usd == 0


@pytest.mark.parametrize("duration", ["NaN", "Infinity", "0", "-1", "301", True, 1.1])
def test_billing_rejects_invalid_duration(duration):
    with pytest.raises(ValueError):
        tariff().estimate(duration)


def test_models_hide_content_in_repr_and_preserve_transcript():
    result = SpeechToTextResult(
        text=" Sí\n", duration_seconds="1", call_id=uuid4(), usage_event_id=uuid4()
    )
    assert result.text == " Sí\n"
    assert "Sí" not in repr(result)
    assert "synthetic-not-decoded" not in repr(inspected())
    assert "private-user" not in repr(origin())
    with pytest.raises(ValidationError):
        result.text = "changed"
