"""Governed single-attempt STT over the private LiteLLM transcription endpoint."""

import asyncio
import json
import time
from collections.abc import Awaitable, Callable
from uuid import UUID

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from src.agent.ancora_agent import _litellm_v1_base_url
from src.config import Settings
from src.domain.llm_access.models import (
    ExecutionContext,
    GovernanceViolationError,
    LlmUsageEventCreate,
)
from src.domain.speech.models import SpeechToTextResult, ValidatedVoiceAudio
from src.domain.speech.service import VoicePreparationError
from src.repositories.llm_usage import LlmUsageRepository


class GovernedSpeechAccess:
    """No direct provider, retries, redirects or fallback; no provider bodies in errors.

    The preparation service owns the duration reservation. This adapter persists
    the usage intent before sending, so cancellation/process death still accrues
    estimated spend. Actual cost is deliberately unknown, not invented.
    """

    def __init__(
        self,
        settings: Settings,
        session_factory: Callable[[], Awaitable[AsyncSession]],
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        if not settings.litellm_proxy_enabled:
            raise ValueError("speech_requires_private_gateway")
        self._settings = settings
        self._sessions = session_factory
        self._transport = transport

    async def transcribe(
        self, audio: ValidatedVoiceAudio, *, execution_context: ExecutionContext, call_id: UUID
    ) -> SpeechToTextResult:
        context = execution_context
        context.budget.ensure_alive()
        speech = context.config.config.speech
        if speech is None:
            raise GovernanceViolationError("speech_route_unavailable")
        route = context.config.config.routing.routes[speech.logical_route]
        estimate = speech.billing.estimate(audio.duration_seconds)
        session = await self._sessions()
        try:
            await LlmUsageRepository(session).record(
                LlmUsageEventCreate(
                    interaction_id=context.correlation_id,
                    llm_call_id=call_id,
                    config_revision=context.config.revision,
                    logical_route=speech.logical_route,
                    effective_gateway_route=route.effective_gateway_route,
                    provider="litellm",
                    model=route.effective_gateway_route,
                    estimated_cost=float(estimate.estimated_cost_usd),
                    cost_source="speech_tariff_snapshot",
                    status="started",
                )
            )
        finally:
            await session.close()
        started = time.monotonic()
        status = "failed_ambiguous"
        try:
            headers = {
                "Authorization": f"Bearer {self._settings.litellm_proxy_virtual_key}",
                "x-ancora-call-id": str(call_id),
                "x-ancora-correlation-id": str(context.correlation_id),
                "x-ancora-config-revision": str(context.config.revision),
            }
            if context.traceparent:
                headers["traceparent"] = context.traceparent
            timeout = min(
                context.budget.seconds_remaining(),
                context.config.config.gateway.request_timeout_seconds,
            )
            async with httpx.AsyncClient(
                transport=self._transport, timeout=timeout, follow_redirects=False
            ) as client:
                request = client.build_request(
                    "POST",
                    f"{_litellm_v1_base_url(self._settings.litellm_proxy_base_url).rstrip('/')}/audio/transcriptions",
                    headers=headers,
                    data={"model": route.effective_gateway_route, "response_format": "json"},
                    files={"file": ("voice.ogg", audio.content, "audio/ogg")},
                )
                response = await client.send(request, stream=True)
                try:
                    if response.status_code != 200:
                        raise VoicePreparationError("stt_gateway_failed", ambiguous=True)
                    body = bytearray()
                    async for chunk in response.aiter_bytes():
                        body.extend(chunk)
                        if len(body) > 131072:
                            raise VoicePreparationError("stt_result_invalid", ambiguous=True)
                    payload = json.loads(body)
                    result = SpeechToTextResult(
                        text=payload["text"],
                        duration_seconds=audio.duration_seconds,
                        call_id=call_id,
                        usage_event_id=call_id,
                    )
                    status = "completed"
                    return result
                finally:
                    await response.aclose()
        except asyncio.CancelledError:
            raise
        except Exception:
            raise VoicePreparationError("stt_gateway_failed", ambiguous=True) from None
        finally:
            session = await self._sessions()
            try:
                await LlmUsageRepository(session).finish_speech_call(
                    context.correlation_id,
                    call_id,
                    status=status,
                    latency_ms=int((time.monotonic() - started) * 1000),
                )
            finally:
                await session.close()
