"""VoicePreparationService.prepare() error-path audit (specs/028 V14/V16/V19).

Exercises the orchestration logic directly with a mocked repository/inspector/
STT port: aggregate budget exhaustion must block the STT request entirely
(V14), a Gateway/timeout failure after sending must be ambiguous without any
retry (V16), and a result that cannot be persisted must stay ambiguous
without replaying the STT call (V19). test_speech_access.py already covers
the Gateway HTTP contract itself; this file covers the preparation service
that sits in front of it.
"""

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from cryptography.fernet import Fernet

from src.domain.interactions.media import TelegramAttachment
from src.domain.interactions.models import InteractionStatus, TelegramInteraction
from src.domain.interactions.payloads import TelegramPayloadCipher
from src.domain.llm_access.models import ExecutionBudgetExceededError
from src.domain.speech.models import InspectedVoiceAudio, SpeechToTextResult
from src.domain.speech.service import VoicePreparationError, VoicePreparationService
from tests.unit.test_speech_access import context as speech_context

_REPO_TARGET = "src.domain.speech.service.VoicePreparationsRepository"


def _interaction() -> TelegramInteraction:
    now = datetime.now(UTC)
    return TelegramInteraction(
        id=uuid4(),
        bot_id=1,
        telegram_update_id=1,
        telegram_message_id=1,
        chat_id=1,
        telegram_user_id=42,
        update_type="message",
        status=InteractionStatus.ACCEPTED,
        received_at=now,
        updated_at=now,
    )


def _attachment() -> TelegramAttachment:
    return TelegramAttachment(kind="voice", file_id="voice-file", duration_seconds=2)


def _service(
    *, stt: AsyncMock, timeout_seconds: float = 60
) -> VoicePreparationService:
    session = AsyncMock()
    sessions = AsyncMock(return_value=session)
    cipher = TelegramPayloadCipher(Fernet.generate_key().decode(), 1)
    inspector = AsyncMock()
    inspector.inspect.return_value = InspectedVoiceAudio(
        content=b"OggSsynthetic",
        mime_type="audio/ogg",
        codec="opus",
        duration_seconds="2",
    )
    download = AsyncMock(return_value=b"OggSsynthetic")
    return VoicePreparationService(
        session_factory=sessions,
        cipher=cipher,
        inspector=inspector,
        stt=stt,
        download=download,
        timeout_seconds=timeout_seconds,
    )


def _repo(**overrides: object) -> AsyncMock:
    repo = AsyncMock()
    for name, value in overrides.items():
        getattr(repo, name).return_value = value
    return repo


async def _transcribe_echo(
    _audio: object, *, execution_context: object, call_id: object
) -> SpeechToTextResult:
    return SpeechToTextResult(
        text="nota de voz privada",
        duration_seconds="2",
        call_id=call_id,
        usage_event_id=uuid4(),
    )


async def test_budget_exhaustion_blocks_stt_request_v14():
    """V14: an exhausted aggregate/reservation budget sends zero STT requests."""
    ctx = await speech_context()
    ctx.budget.model_calls = ctx.budget.max_model_calls  # pre-exhaust the ceiling
    stt = AsyncMock()
    repo = _repo()
    service = _service(stt=stt)

    with patch(_REPO_TARGET, return_value=repo), pytest.raises(VoicePreparationError) as error:
        await service.prepare(_interaction(), _attachment(), context=ctx)

    assert error.value.ambiguous is False  # nothing was sent, so safe to not replay
    stt.transcribe.assert_not_awaited()
    repo.start_transcription.assert_not_awaited()


async def test_budget_error_type_is_translated_without_leaking():
    """The raw ExecutionBudgetExceededError is never exposed to the caller."""
    ctx = await speech_context()
    ctx.budget.model_calls = ctx.budget.max_model_calls
    stt = AsyncMock()
    repo = _repo()
    service = _service(stt=stt)

    with patch(_REPO_TARGET, return_value=repo), pytest.raises(VoicePreparationError):
        await service.prepare(_interaction(), _attachment(), context=ctx)

    with pytest.raises(ExecutionBudgetExceededError):
        ctx.budget.reserve_model_call(0.0)  # confirms the ceiling really is exhausted


async def test_stt_timeout_is_ambiguous_without_retry_v16():
    """V16: a Gateway timeout after sending is ambiguous, with exactly one attempt."""
    ctx = await speech_context()

    async def slow_transcribe(*_args: object, **_kwargs: object) -> SpeechToTextResult:
        await asyncio.sleep(1)
        raise AssertionError("must not resolve past the preparation timeout")

    stt = AsyncMock()
    stt.transcribe.side_effect = slow_transcribe
    repo = _repo()
    service = _service(stt=stt, timeout_seconds=0.05)

    with patch(_REPO_TARGET, return_value=repo), pytest.raises(VoicePreparationError) as error:
        await service.prepare(_interaction(), _attachment(), context=ctx)

    assert error.value.code == "stt_timeout"
    assert error.value.ambiguous is True  # already sent; must not auto-retry
    stt.transcribe.assert_awaited_once()


async def test_stt_gateway_failure_propagates_ambiguous_without_retry_v16():
    """V16: a Gateway-reported failure after sending is ambiguous, one attempt only."""
    ctx = await speech_context()
    stt = AsyncMock()
    stt.transcribe.side_effect = VoicePreparationError("stt_gateway_failed", ambiguous=True)
    repo = _repo()
    service = _service(stt=stt)

    with patch(_REPO_TARGET, return_value=repo), pytest.raises(VoicePreparationError) as error:
        await service.prepare(_interaction(), _attachment(), context=ctx)

    assert error.value.code == "stt_gateway_failed"
    assert error.value.ambiguous is True
    stt.transcribe.assert_awaited_once()
    repo.persist_transcript.assert_not_awaited()


async def test_persist_transcript_failure_keeps_ambiguous_without_replay_v19():
    """V19: a failed persist after a successful STT call is ambiguous, no replay."""
    ctx = await speech_context()
    stt = AsyncMock()
    stt.transcribe.side_effect = _transcribe_echo
    repo = _repo(persist_transcript=None)  # simulates a lost/ambiguous write
    service = _service(stt=stt)

    with patch(_REPO_TARGET, return_value=repo), pytest.raises(VoicePreparationError) as error:
        await service.prepare(_interaction(), _attachment(), context=ctx)

    assert error.value.code == "stt_result_ambiguous"
    assert error.value.ambiguous is True
    stt.transcribe.assert_awaited_once()  # the STT call itself is never replayed


async def test_mismatched_call_id_rejected_without_persisting():
    """A result that does not match the reserved call_id is never persisted."""
    ctx = await speech_context()
    stt = AsyncMock()
    stt.transcribe.return_value = SpeechToTextResult(
        text="nota de voz privada",
        duration_seconds="2",
        call_id=uuid4(),  # deliberately different from the reserved call_id
        usage_event_id=uuid4(),
    )
    repo = _repo()
    service = _service(stt=stt)

    with patch(_REPO_TARGET, return_value=repo), pytest.raises(VoicePreparationError) as error:
        await service.prepare(_interaction(), _attachment(), context=ctx)

    assert error.value.code == "stt_result_invalid"
    assert error.value.ambiguous is True
    repo.persist_transcript.assert_not_awaited()


async def test_mark_downloaded_failure_blocks_stt_without_ambiguity():
    """A lost preparation row before sending fails controlled, not ambiguous."""
    ctx = await speech_context()
    stt = AsyncMock()
    repo = _repo(mark_downloaded=None)
    service = _service(stt=stt)

    with patch(_REPO_TARGET, return_value=repo), pytest.raises(VoicePreparationError) as error:
        await service.prepare(_interaction(), _attachment(), context=ctx)

    assert error.value.code == "voice_transition_failed"
    assert error.value.ambiguous is False
    stt.transcribe.assert_not_awaited()


@pytest.mark.parametrize("sent", [False, True])
async def test_failure_closes_own_preparation_row_without_stt_replay(sent):
    """A failed preparation must not leave its row in a non-terminal state."""
    from src.domain.speech.policy import SpeechInputError

    ctx = await speech_context()
    stt = AsyncMock()
    stt.transcribe.side_effect = _transcribe_echo
    repo = _repo()
    service = _service(stt=stt)
    if sent:
        repo.persist_transcript.side_effect = RuntimeError("boom")
    else:
        service._inspector.inspect.side_effect = SpeechInputError("voice_probe_failed")

    with patch(_REPO_TARGET, return_value=repo), pytest.raises(VoicePreparationError) as error:
        await service.prepare(_interaction(), _attachment(), context=ctx)

    assert error.value.ambiguous is sent
    repo.close_failed.assert_awaited_once()
    assert repo.close_failed.call_args.kwargs == {"ambiguous": sent}
    assert stt.transcribe.await_count == (1 if sent else 0)


async def test_close_failure_never_masks_original_error():
    ctx = await speech_context()
    stt = AsyncMock()
    repo = _repo()
    repo.close_failed.side_effect = RuntimeError("db down")
    service = _service(stt=stt)
    service._inspector.inspect.side_effect = RuntimeError("inspect")

    with patch(_REPO_TARGET, return_value=repo), pytest.raises(VoicePreparationError) as error:
        await service.prepare(_interaction(), _attachment(), context=ctx)

    assert error.value.code == "stt_failed"


async def test_claim_miss_returns_none_without_stt():
    """Another worker already owns this preparation: no STT, no exception."""
    ctx = await speech_context()
    stt = AsyncMock()
    repo = _repo(claim=None)
    service = _service(stt=stt)

    with patch(_REPO_TARGET, return_value=repo):
        result = await service.prepare(_interaction(), _attachment(), context=ctx)

    assert result is None
    stt.transcribe.assert_not_awaited()


async def test_happy_path_returns_transcribed_text():
    ctx = await speech_context()
    stt = AsyncMock()
    stt.transcribe.side_effect = _transcribe_echo
    repo = _repo()
    service = _service(stt=stt)

    with patch(_REPO_TARGET, return_value=repo):
        result = await service.prepare(_interaction(), _attachment(), context=ctx)

    assert result == "nota de voz privada"
    repo.persist_transcript.assert_awaited_once()
