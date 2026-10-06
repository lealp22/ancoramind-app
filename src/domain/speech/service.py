"""Exclusive speech preparation; no SDKs, files, or automatic STT replay."""

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.interactions.media import TelegramAttachment
from src.domain.interactions.models import TelegramInteraction
from src.domain.interactions.payloads import TelegramPayloadCipher
from src.domain.llm_access.context import execution_context_scope
from src.domain.llm_access.models import ExecutionContext
from src.domain.speech.models import SpeechToTextResult
from src.domain.speech.policy import SpeechBillingPolicy, SpeechInputError, SpeechInputPolicy
from src.domain.speech.ports import SpeechToTextPort, VoiceAudioInspectorPort
from src.domain.speech.preparation import SpeechTranscriptCipher
from src.repositories.voice_preparations import VoicePreparationsRepository


class VoicePreparationError(RuntimeError):
    """Fixed metadata code and conservative post-send ambiguity."""

    def __init__(self, code: str, *, ambiguous: bool = False):
        super().__init__(code)
        self.code = code
        self.ambiguous = ambiguous


class VoicePreparationService:
    """Only explicitly injected test/physical adapters can provide transcription."""

    def __init__(
        self,
        *,
        session_factory: Callable[[], Awaitable[AsyncSession]],
        cipher: TelegramPayloadCipher,
        inspector: VoiceAudioInspectorPort,
        stt: SpeechToTextPort,
        download: Callable[[TelegramAttachment], Awaitable[bytes]],
        billing: SpeechBillingPolicy | None = None,
        logical_route: str | None = None,
        effective_route: str | None = None,
        timeout_seconds: float = 60,
    ):
        if not 0 < timeout_seconds <= 120:
            raise ValueError("invalid voice timeout")
        self._sessions = session_factory
        self._cipher = SpeechTranscriptCipher(cipher)
        self._inspector = inspector
        self._stt = stt
        self._download = download
        self._billing = billing
        self._logical_route = logical_route
        self._effective_route = effective_route
        self._timeout = timeout_seconds
        self.policy = SpeechInputPolicy(enabled=True)

    @asynccontextmanager
    async def exclusive(self, interaction_id: UUID) -> AsyncIterator[bool]:
        """Keep dedicated transaction alive through STT AND the Agent claim."""
        session = await self._sessions()
        try:
            yield await VoicePreparationsRepository(session).try_preparation_lock(interaction_id)
        finally:
            await session.close()  # rollback releases the transaction advisory lock

    async def prepare(
        self,
        interaction: TelegramInteraction,
        attachment: TelegramAttachment,
        *,
        context: ExecutionContext,
    ) -> str | None:
        if interaction.telegram_user_id is None:
            raise VoicePreparationError("voice_origin_not_allowed")
        user_id = interaction.telegram_user_id
        owner = uuid4()
        session = await self._sessions()
        sent = False
        content = None
        audio = None
        try:
            speech = context.config.config.speech
            billing = speech.billing if speech else self._billing
            logical_route = speech.logical_route if speech else self._logical_route
            effective_route = (
                context.config.config.routing.routes[speech.logical_route].effective_gateway_route
                if speech else self._effective_route
            )
            if billing is None or logical_route is None or effective_route is None:
                raise VoicePreparationError("stt_route_unavailable")
            repo = VoicePreparationsRepository(session)
            claimed = await repo.claim(interaction.id, user_id, owner, context.config.revision)
            if claimed is None:
                return None
            async with asyncio.timeout(min(self._timeout, context.budget.seconds_remaining())):
                content = await self._download(attachment)
                audio = self.policy.validate_audio(await self._inspector.inspect(content))
                content = None
                if await repo.mark_downloaded(interaction.id, user_id, owner) is None:
                    raise VoicePreparationError("voice_transition_failed")
                call_id = uuid4()
                estimate = billing.estimate(audio.duration_seconds)
                context.budget.reserve_model_call(float(estimate.estimated_cost_usd))
                if (
                    await repo.start_transcription(
                        interaction.id,
                        user_id,
                        owner,
                        call_id=call_id,
                        logical_route=logical_route,
                        effective_route=effective_route,
                        audio=audio,
                        estimate=estimate,
                    )
                    is None
                ):
                    raise VoicePreparationError("voice_transition_failed")
                sent = True
                with execution_context_scope(context):
                    result = await self._stt.transcribe(
                        audio, execution_context=context, call_id=call_id
                    )
                audio = None
                if not isinstance(result, SpeechToTextResult):
                    raise VoicePreparationError("stt_result_invalid", ambiguous=True)
                if result.call_id != call_id:
                    raise VoicePreparationError("stt_result_invalid", ambiguous=True)
                if (
                    await repo.persist_transcript(
                        interaction.id,
                        user_id,
                        owner,
                        result=result,
                        cipher=self._cipher,
                    )
                    is None
                ):
                    raise VoicePreparationError("stt_result_ambiguous", ambiguous=True)
                return result.text
        except asyncio.CancelledError:
            raise
        except VoicePreparationError:
            raise
        except SpeechInputError as exc:
            raise VoicePreparationError(exc.code, ambiguous=sent) from None
        except TimeoutError:
            raise VoicePreparationError("stt_timeout", ambiguous=sent) from None
        except Exception:
            raise VoicePreparationError("stt_failed", ambiguous=sent) from None
        finally:
            content = None
            audio = None
            await session.close()

    async def maintain(self) -> int:
        return await maintain_voice_preparations(self._sessions)


async def maintain_voice_preparations(
    sessions: Callable[[], Awaitable[AsyncSession]],
) -> int:
    """Recover only unlocked abandoned owners; never reclaim active workers."""
    session = await sessions()
    try:
        scopes = await VoicePreparationsRepository(session).maintenance_scopes()
    finally:
        await session.close()
    count = 0
    for interaction_id, user_id, owner in scopes:
        lock_session = await sessions()
        try:
            if not await VoicePreparationsRepository(lock_session).try_preparation_lock(
                interaction_id
            ):
                continue
            session = await sessions()
            try:
                repo = VoicePreparationsRepository(session)
                now = datetime.now(UTC)
                count += await repo.recover_abandoned(
                    user_id=user_id, owner_token=owner, updated_before=now
                )
                await repo.purge_expired_transcripts(user_id=user_id, now=now)
            finally:
                await session.close()
        finally:
            await lock_session.close()
    return count
