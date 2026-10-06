"""Domain-owned ports; physical clients/decoders belong in infrastructure."""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

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

    The orchestrator reserves cost/call budget before invoking this port.
    Implementations record usage even without an Agent run, preserve the supplied
    call_id, and fail closed without provider fallback or automatic retries.
    """

    async def transcribe(
        self, audio: ValidatedVoiceAudio, *, execution_context: ExecutionContext, call_id: UUID
    ) -> SpeechToTextResult: ...
