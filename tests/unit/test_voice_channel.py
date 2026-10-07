"""T4 voice dispatch uses fake STT, never documents or synthetic controls."""

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock

import httpx
import pytest

from src.agent.telegram_media import TelegramMediaResolver
from src.config import Settings
from src.domain.interactions.models import normalize_telegram_update
from src.domain.interactions.processor import InteractionProcessor
from src.domain.speech.policy import SpeechInputPolicy
from src.domain.speech.service import VoicePreparationError
from tests.unit.test_interaction_processor import _interaction


def update(**changes):
    message = {
        "message_id": 3,
        "chat": {"id": 4, "type": "private"},
        "from": {"id": 5},
        "voice": {"file_id": "synthetic", "duration": 300},
    }
    message.update(changes)
    return {"update_id": 2, "message": message}


@pytest.mark.parametrize(
    "changes,kind",
    [({}, "original"), ({"forward_origin": {}}, "forwarded"), ({"caption": "x"}, "mixed")],
)
def test_normalization_provenance(changes, kind):
    result = normalize_telegram_update(update(**changes))
    assert result.voice_message_kind == kind
    assert result.attachments[0].kind == "voice"
    assert result.attachments[0].duration_seconds == 300


@asynccontextmanager
async def exclusive(_):
    yield True


@pytest.mark.parametrize("text", ["consulta mis notas", "/new", "ancora:confirm:fake"])
async def test_voice_goes_to_agent_as_text_not_command_or_media(text):
    from cryptography.fernet import Fernet

    from src.domain.interactions.payloads import TelegramPayloadCipher

    cipher = TelegramPayloadCipher(Fernet.generate_key().decode(), 1)
    normalized = normalize_telegram_update(update())
    payload = normalized.model_dump(mode="json")
    interaction = _interaction().model_copy(
        update={"payload_ciphertext": cipher.encrypt(payload).ciphertext}
    )
    service = AsyncMock()
    service.policy = SpeechInputPolicy(enabled=True)
    service.exclusive = exclusive
    service.prepare.return_value = text
    runner = AsyncMock()
    processor = InteractionProcessor(
        session_factory=AsyncMock(),
        payload_cipher=cipher,
        agent_runner=runner,
        sender=AsyncMock(),
        voice_enabled=True,
        voice_preparation=service,
    )
    processor._conversation_session_id = AsyncMock(return_value="session")
    processor._claim_agent = AsyncMock(return_value=None)
    processor._handle_command = AsyncMock()
    await processor._run_agent(interaction)
    service.prepare.assert_awaited_once()
    processor._claim_agent.assert_awaited_once()
    processor._handle_command.assert_not_awaited()


@pytest.mark.parametrize("enabled,text", [(False, "hola"), (True, "Sí"), (True, "No.")])
async def test_disabled_and_consent_do_not_start_agent(enabled, text):
    processor = InteractionProcessor(
        session_factory=AsyncMock(),
        payload_cipher=AsyncMock(),
        agent_runner=AsyncMock(),
        sender=AsyncMock(),
        voice_enabled=enabled,
    )
    service = AsyncMock()
    service.policy = SpeechInputPolicy(enabled=True)
    service.exclusive = exclusive
    service.prepare.return_value = text
    processor._voice_preparation = service
    processor._conversation_session_id = AsyncMock(return_value="session")
    processor._reply_deterministically = AsyncMock(return_value=True)
    processor._claim_agent = AsyncMock()
    normalized = normalize_telegram_update(update())
    await processor._prepare_voice(
        _interaction(), normalized.attachments[0], normalized.model_dump(mode="json")
    )
    processor._reply_deterministically.assert_awaited_once()
    processor._claim_agent.assert_not_awaited()
    if not enabled:
        service.prepare.assert_not_awaited()


@pytest.mark.parametrize("ambiguous", [False, True])
async def test_stt_failure_never_starts_agent(ambiguous):
    service = AsyncMock()
    service.policy = SpeechInputPolicy(enabled=True)
    service.exclusive = exclusive
    service.prepare.side_effect = VoicePreparationError("stt_failed", ambiguous=ambiguous)
    processor = InteractionProcessor(
        session_factory=AsyncMock(),
        payload_cipher=AsyncMock(),
        agent_runner=AsyncMock(),
        sender=AsyncMock(),
        voice_enabled=True,
        voice_preparation=service,
    )
    processor._conversation_session_id = AsyncMock(return_value="session")
    processor._mark_terminal = AsyncMock()
    processor._reply_deterministically = AsyncMock(return_value=True)
    normalized = normalize_telegram_update(update())
    await processor._prepare_voice(
        _interaction(), normalized.attachments[0], normalized.model_dump(mode="json")
    )
    assert processor._mark_terminal.await_args.args[1].value == (
        "failed_ambiguous" if ambiguous else "failed_controlled"
    )
    processor._agent_runner.run.assert_not_awaited()
    service.prepare.assert_awaited_once()
    if ambiguous:
        processor._reply_deterministically.assert_awaited_once()
        assert processor._reply_deterministically.call_args.args[1] == (
            "No he podido entender el audio. Por favor, envía tus indicaciones de nuevo."
        )
    else:
        processor._reply_deterministically.assert_not_awaited()


async def test_stream_download_checks_actual_bytes_and_closes():
    class Stream(httpx.AsyncByteStream):
        closed = False

        async def __aiter__(self):
            yield b"OggS"
            yield b"overflow"

        async def aclose(self):
            self.closed = True

    stream = Stream()

    def handler(request):
        if request.url.path.endswith("getFile"):
            return httpx.Response(200, json={"ok": True, "result": {"file_path": "voice/a.ogg"}})
        return httpx.Response(200, stream=stream)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        resolver = TelegramMediaResolver(Settings(_env_file=None), client=client)
        attachment = normalize_telegram_update(update()).attachments[0]
        with pytest.raises(Exception, match="voice_too_large"):
            await resolver.resolve_voice(attachment, max_bytes=5)
    assert stream.closed


@pytest.mark.parametrize(
    "changes",
    [
        {"voice": {"file_id": "synthetic", "duration": 301}},
        {"voice": {"file_id": "synthetic", "duration": 2, "file_size": 10_485_761}},
        {"voice": {"file_id": "synthetic"}},
        {"forward_origin": {}},
        {"caption": "mixed"},
    ],
)
async def test_invalid_reference_never_downloads(changes):
    service = AsyncMock()
    service.policy = SpeechInputPolicy(enabled=True)
    processor = InteractionProcessor(
        session_factory=AsyncMock(),
        payload_cipher=AsyncMock(),
        agent_runner=AsyncMock(),
        sender=AsyncMock(),
        voice_enabled=True,
        voice_preparation=service,
    )
    processor._mark_terminal = AsyncMock()
    normalized = normalize_telegram_update(update(**changes))
    await processor._prepare_voice(
        _interaction(), normalized.attachments[0], normalized.model_dump(mode="json")
    )
    service.prepare.assert_not_awaited()
    processor._agent_runner.run.assert_not_awaited()
    processor._mark_terminal.assert_awaited_once()


def test_malformed_voice_cannot_fall_back_to_document():
    with pytest.raises(ValueError, match="invalid Telegram voice reference"):
        normalize_telegram_update(update(voice={"duration": 5}, document={"file_id": "doc"}))
