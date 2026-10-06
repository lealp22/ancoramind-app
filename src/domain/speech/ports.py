"""Domain-owned ports; physical clients/decoders belong in infrastructure."""

from __future__ import annotations

from typing import Protocol

from src.domain.llm_access.models import ExecutionContext
from src.domain.speech.models import InspectedVoiceAudio, SpeechToTextResult, ValidatedVoiceAudio


class VoiceAudioInspectorPort(Protocol):
    """Inspect bounded local bytes, validating container, codec and real duration.

    Implementations must reject corrupt/multiple-stream input and bound runtime,
    memory and output. Header sniffing alone does not satisfy this contract.
    """

    async def inspect(self, content: bytes) -> InspectedVoiceAudio: ...


class SpeechToTextPort(Protocol):
    """STT through governed access with the interaction snapshot and budget.

    Implementations reserve cost before sending, record usage even without an
    Agent run, and fail closed without provider fallback or automatic retries.
    """

    async def transcribe(
        self, audio: ValidatedVoiceAudio, *, execution_context: ExecutionContext
    ) -> SpeechToTextResult: ...
