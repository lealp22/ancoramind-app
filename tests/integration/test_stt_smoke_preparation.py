"""Exercise the smoke orchestration with real PostgreSQL, never real inference."""

from unittest.mock import AsyncMock

import httpx
import pytest

from src.agent.speech_access import GovernedSpeechAccess
from src.domain.speech.models import InspectedVoiceAudio
from tests.integration import test_stt_live_smoke as smoke
from tests.unit.test_stt_smoke_config import approved_env

pytestmark = pytest.mark.integration


async def test_smoke_path_offline(session, tmp_path, monkeypatch):
    for name, value in approved_env(tmp_path).items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv("ANCORA_STT_SMOKE_VIRTUAL_KEY", "synthetic-key")
    inspector = AsyncMock()
    inspector.inspect.return_value = InspectedVoiceAudio(
        content=b"OggSsynthetic",
        mime_type="audio/ogg",
        codec="opus",
        duration_seconds="2",
    )
    monkeypatch.setattr(smoke, "FFmpegVoiceInspector", lambda: inspector)
    requests = []

    def handle(request):
        requests.append(request)
        return httpx.Response(200, json={"text": "synthetic smoke"})

    monkeypatch.setattr(
        smoke,
        "GovernedSpeechAccess",
        lambda settings, factory: GovernedSpeechAccess(
            settings, factory, transport=httpx.MockTransport(handle)
        ),
    )
    await smoke.test_live_governed_stt(session)
    assert len(requests) == 1
