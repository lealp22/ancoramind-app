"""Gateway STT contract without credentials, network or inference."""

import asyncio
import json
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import httpx
import pytest

from src.agent.speech_access import GovernedSpeechAccess
from src.config import Settings
from src.domain.runtime_config.models import RuntimeConfiguration, config_checksum
from src.domain.speech.models import ValidatedVoiceAudio
from src.domain.speech.service import VoicePreparationError
from tests.unit.test_governed_interaction_runner import _runner


async def context():
    runner, _ = _runner()
    ctx = await runner.prepare_execution_context(
        session_id="test",
        run_id="test",
        correlation_id=uuid4(),
        telegram_update_id=2,
    )
    payload = ctx.config.config.model_dump(mode="json", by_alias=True)
    payload["routing"]["routes"]["speech-test"] = {
        "effective_gateway_route": "speech-test-r1",
        "capabilities": ["transcription"],
    }
    payload["speech"] = {
        "logical_route": "speech-test",
        "billing": {
            "version": "fake-r1",
            "rate_usd_per_second": "0",
            "quantum_seconds": "1",
            "minimum_seconds": "0",
        },
    }
    config = RuntimeConfiguration.model_validate(payload)
    from dataclasses import replace

    return replace(
        ctx,
        config=ctx.config.model_copy(
            update={"config": config, "checksum": config_checksum(config)}
        ),
    )


@pytest.mark.parametrize("kind", ["ok", "error", "redirect", "invalid", "oversized", "cancel"])
async def test_single_request_and_metadata_only_audit(kind):
    ctx = await context()
    call_id = uuid4()
    audio = ValidatedVoiceAudio(content=b"OggSsynthetic", duration_seconds="2")
    seen = []

    async def handle(request):
        seen.append(request)
        assert request.url.path == "/v1/audio/transcriptions"
        assert b"speech-test-r1" in request.content and b"voice.ogg" in request.content
        assert request.headers["x-ancora-call-id"] == str(call_id)
        if kind == "cancel":
            raise asyncio.CancelledError()
        if kind == "error":
            return httpx.Response(500, text="PERSONAL PROVIDER ERROR")
        if kind == "redirect":
            return httpx.Response(307, headers={"location": "https://untrusted.invalid"})
        if kind == "invalid":
            return httpx.Response(200, json={"text": " "})
        if kind == "oversized":
            return httpx.Response(200, text="x" * 140000)
        return httpx.Response(200, json={"text": "consulta privada"})

    settings = Settings(
        _env_file=None,
        litellm_proxy_enabled=True,
        litellm_proxy_base_url="http://gateway.invalid/v1",
        litellm_proxy_virtual_key="synthetic",
    )
    repository = AsyncMock()
    with patch("src.agent.speech_access.LlmUsageRepository", return_value=repository):
        adapter = GovernedSpeechAccess(
            settings, AsyncMock(return_value=AsyncMock()), transport=httpx.MockTransport(handle)
        )
        if kind == "ok":
            assert (
                await adapter.transcribe(audio, execution_context=ctx, call_id=call_id)
            ).text == "consulta privada"
        else:
            with pytest.raises(
                asyncio.CancelledError if kind == "cancel" else VoicePreparationError
            ) as error:
                await adapter.transcribe(audio, execution_context=ctx, call_id=call_id)
            assert "PERSONAL" not in str(error.value)
    assert len(seen) == 1
    event = repository.record.call_args.args[0]
    assert "consulta privada" not in json.dumps(event.model_dump(mode="json"))
    repository.finish_speech_call.assert_awaited_once()


async def test_audit_failure_prevents_request():
    ctx = await context()
    repository = AsyncMock()
    repository.record.side_effect = RuntimeError("audit unavailable")
    transport = AsyncMock()
    settings = Settings(
        _env_file=None,
        litellm_proxy_enabled=True,
        litellm_proxy_base_url="http://gateway.invalid/v1",
        litellm_proxy_virtual_key="synthetic",
    )
    with (
        patch("src.agent.speech_access.LlmUsageRepository", return_value=repository),
        pytest.raises(RuntimeError),
    ):
        await GovernedSpeechAccess(
            settings, AsyncMock(return_value=AsyncMock()), transport=transport
        ).transcribe(
            ValidatedVoiceAudio(content=b"OggSsynthetic", duration_seconds="2"),
            execution_context=ctx,
            call_id=uuid4(),
        )
    transport.handle_async_request.assert_not_awaited()


def test_legacy_config_checksum_stays_compatible():
    import hashlib

    from src.domain.runtime_config.models import bootstrap_runtime_configuration

    config = bootstrap_runtime_configuration()
    payload = config.model_dump(mode="json", by_alias=True)
    payload.pop("speech")
    expected = hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    assert config_checksum(config) == expected
