"""Deterministic processor for accepted interactions and the logical-response outbox."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections import defaultdict
from collections.abc import Awaitable, Callable, Sequence
from datetime import UTC, datetime
from typing import Any, Protocol
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.actions.executor import ProposalExecutor
from src.domain.actions.models import ConsentClaimResult, ConsentPrincipal, ConsentRejection
from src.domain.actions.presentation import (
    ConsentAction,
    ConsentButton,
    ConsentCallback,
    consent_buttons,
    parse_consent_callback,
    render_proposal_block,
)
from src.domain.context_policy.service import oldest_fraction_count
from src.domain.context_policy.session_summary import SessionExchange, SessionSummarizationPort
from src.domain.emergency_stop.models import EmergencyStopActiveError
from src.domain.interactions.commands import (
    TelegramCommand,
    default_session_id,
    handle_telegram_command,
    next_session_id,
    parse_telegram_command,
    telemetry_label,
)
from src.domain.interactions.consent_intent import parse_consent_intent
from src.domain.interactions.media import (
    AttachmentResolutionError,
    ResolvedTelegramMedia,
    TelegramAttachment,
)
from src.domain.interactions.models import (
    InteractionStatus,
    LogicalResponse,
    TelegramInteraction,
    TelegramResponseDelivery,
    bounded_callback_query_id,
)
from src.domain.interactions.outbox import split_telegram_message
from src.domain.interactions.payloads import TelegramPayloadCipher
from src.domain.interactions.rejection_notice import ACCESS_DENIED_REPLY
from src.domain.interactions.reply import AgentReply, InvalidPresentationOutputError
from src.domain.llm_access.cost_governance import CostGovernanceError
from src.domain.llm_access.models import (
    ExecutionBudgetExceededError,
    ExecutionContext,
    InteractionProvenance,
)
from src.domain.preferences.timezone import resolve_user_timezone
from src.domain.speech.consent import parse_voice_consent_intent
from src.domain.speech.models import VoiceReference
from src.domain.speech.service import VoicePreparationError, VoicePreparationService
from src.observability import get_telemetry, log_context_scope
from src.repositories.actions import ActionProposalsRepository
from src.repositories.interactions import TelegramInteractionsRepository
from src.repositories.llm_usage import LlmUsageRepository
from src.repositories.reminders import RemindersRepository
from src.security.user_context import UserContext

logger = logging.getLogger(__name__)

AGENT_PRESENTATION_FAILURE_NOTICE = (
    "No pude completar una respuesta válida y no reintentaré automáticamente. "
    "Si pediste una acción, consulta primero su estado antes de repetirla."
)
VOICE_NOT_UNDERSTOOD_REPLY = (
    "No he podido entender el audio. Por favor, envía tus indicaciones de nuevo."
)
DOCUMENT_RECEIVED_ACK = "📄 Documento recibido, analizando…"
"""BL-32: fixed, non-personal early acknowledgement for attachment-bearing
interactions — never a template over user content."""
CALLBACK_ACK_TIMEOUT_SECONDS = 2.0
CALLBACK_INVALID_REPLY = (
    "Ese botón no es una confirmación válida. No se ha ejecutado ninguna acción."
)
CALLBACK_DISABLED_REPLY = (
    "La confirmación por botones aún no está habilitada. No se ha ejecutado ninguna acción."
)


class InteractionAgentRunner(Protocol):
    """Infrastructure port for one governed Agent execution (T7 runner)."""

    async def run(
        self,
        input_text: str,
        *,
        user_id: str,
        session_id: str,
        run_id: str,
        correlation_id: UUID,
        telegram_update_id: int,
        telegram_message_id: int | None = None,
        media: tuple[ResolvedTelegramMedia, ...] = (),
        provenance: InteractionProvenance | None = None,
        execution_context: ExecutionContext | None = None,
        compaction_summary: str | None = None,
        reduced_history_runs: int | None = None,
    ) -> str | AgentReply: ...


class TelegramMediaResolverPort(Protocol):
    """Infrastructure port for resolving encrypted Telegram file references."""

    async def resolve(self, attachment: TelegramAttachment) -> ResolvedTelegramMedia: ...


class TelegramResponseSender(Protocol):
    """Outbound Telegram port returning the confirmed Telegram message ID."""

    async def send_text(
        self,
        chat_id: int,
        text: str,
        *,
        button_rows: Sequence[tuple[ConsentButton, ConsentButton]] | None = None,
    ) -> int: ...

    async def send_typing(self, chat_id: int) -> None: ...

    async def answer_callback_query(self, callback_query_id: str) -> bool: ...


class TelegramSendError(RuntimeError):
    """A Telegram send failure classified by whether no external message was sent."""

    def __init__(self, message: str, *, definitive: bool, description: str | None = None):
        super().__init__(message)
        self.definitive = definitive
        self.description = description
        """Telegram's ``description`` field, when the API answered with one."""


def _decrypt_field(
    cipher: TelegramPayloadCipher, ciphertext: bytes | None, field: str
) -> str | None:
    """Best-effort decrypt for BL-34's compaction path — never raises.

    A single corrupt/legacy row must not abort compaction for the whole
    session; it is simply treated as an exchange with nothing to say.
    """
    if ciphertext is None:
        return None
    try:
        value = cipher.decrypt(ciphertext).get(field)
    except ValueError:
        return None
    return value if isinstance(value, str) and value.strip() else None


SessionFactory = Callable[[], Awaitable[AsyncSession]]


class InteractionProcessor:
    """Process durable work without replaying uncertain Agent or Telegram effects."""

    def __init__(
        self,
        *,
        session_factory: SessionFactory,
        payload_cipher: TelegramPayloadCipher,
        agent_runner: InteractionAgentRunner,
        sender: TelegramResponseSender,
        media_resolver: TelegramMediaResolverPort | None = None,
        global_concurrency: int = 2,
        batch_size: int = 20,
        typing_refresh_seconds: float = 4.0,
        bot_username: str | None = None,
        on_cycle: Callable[[int], None] | None = None,
        on_interaction_completed: Callable[[], None] | None = None,
        governed_consent: bool = False,
        voice_enabled: bool = False,
        voice_preparation: VoicePreparationService | None = None,
        voice_maintenance: Callable[[], Awaitable[int]] | None = None,
        fast_ack_enabled: bool = False,
        access_notice_enabled: bool = False,
        summarizer: SessionSummarizationPort | None = None,
        context_compaction_enabled: bool = False,
        context_compaction_token_threshold: int = 60_000,
        context_compaction_ratio: float = 0.4,
        pilot_notice_url: str | None = None,
    ):
        self._pilot_notice_url = pilot_notice_url
        self._session_factory = session_factory
        self._payload_cipher = payload_cipher
        self._agent_runner = agent_runner
        self._sender = sender
        self._media_resolver = media_resolver
        self._global_semaphore = asyncio.Semaphore(global_concurrency)
        self._batch_size = batch_size
        self._typing_refresh_seconds = typing_refresh_seconds
        self._bot_username = bot_username
        self._on_cycle = on_cycle
        self._on_interaction_completed = on_interaction_completed
        self._governed_consent = governed_consent
        self._voice_enabled = voice_enabled
        self._voice_preparation = voice_preparation
        self._voice_maintenance = voice_maintenance
        self._fast_ack_enabled = fast_ack_enabled
        """BL-32: best-effort, off by default; a failure never blocks the run."""
        self._access_notice_enabled = access_notice_enabled
        """specs/023 T4.3-T4.4: off by default; when off, behaviour is unchanged."""
        self._summarizer = summarizer
        self._context_compaction_enabled = context_compaction_enabled
        self._context_compaction_token_threshold = context_compaction_token_threshold
        self._context_compaction_ratio = context_compaction_ratio
        """BL-34: off by default; a compaction failure never blocks the run,
        it only forfeits the summary for that run."""
        self._chat_locks: dict[int, asyncio.Lock] = {}
        self._user_locks: dict[int, asyncio.Lock] = {}

    async def recover_once(self) -> int:
        """Mark states that may already have side effects as ambiguous after restart."""
        if self._voice_preparation is not None:
            await self._voice_preparation.maintain()
        elif self._voice_maintenance is not None:
            await self._voice_maintenance()
        session = await self._session_factory()
        try:
            repository = TelegramInteractionsRepository(session)
            if self._access_notice_enabled:
                await repository.maintain_access_notices(recovering=True)
            return await repository.mark_inflight_as_ambiguous()
        finally:
            await session.close()

    async def run_once(self) -> int:
        """Recover deterministic work ordered by chat, with bounded parallel chats."""
        if self._voice_preparation is not None:
            await self._voice_preparation.maintain()
        elif self._voice_maintenance is not None:
            await self._voice_maintenance()
        session = await self._session_factory()
        try:
            notices = await TelegramInteractionsRepository(session).list_voice_failure_notices(
                self._batch_size
            )
            interactions = await TelegramInteractionsRepository(session).list_recoverable_work(
                self._batch_size
            )
        finally:
            await session.close()

        for interaction in notices:
            await self._reply_deterministically(
                interaction, VOICE_NOT_UNDERSTOOD_REPLY, voice_failure_notice=True
            )

        grouped: dict[int, list[TelegramInteraction]] = defaultdict(list)
        for interaction in interactions:
            chat_key = interaction.chat_id if interaction.chat_id is not None else -1
            grouped[chat_key].append(interaction)

        results: list[int | BaseException] = list(
            await asyncio.gather(
                *(self._process_chat_queue(queue) for queue in grouped.values()),
                return_exceptions=True,
            )
        )
        processed = 0
        for result in results:
            if isinstance(result, BaseException):
                logger.exception("Interaction chat queue failed", exc_info=result)
            else:
                processed += result
        if self._access_notice_enabled:
            processed += await self._deliver_access_notices()
        return processed

    async def _deliver_access_notices(self) -> int:
        """Drain bounded secondary outbox, never process rejected input or tools."""
        session = await self._session_factory()
        try:
            repo = TelegramInteractionsRepository(session)
            await repo.maintain_access_notices()
            notices = await repo.list_access_notices(self._batch_size)
        finally:
            await session.close()
        sent = 0
        for interaction, delivery_id in notices:
            if interaction.chat_id is None:  # defensive; admission requires identity
                continue
            session = await self._session_factory()
            try:
                claimed = await TelegramInteractionsRepository(session).claim_access_notice(
                    delivery_id
                )
            finally:
                await session.close()
            if not claimed:
                continue
            try:
                message_id = await self._sender.send_text(interaction.chat_id, ACCESS_DENIED_REPLY)
            except asyncio.CancelledError:
                # Claim is durable: recovery records ambiguity and never resends.
                raise
            except Exception as exc:
                await self._record_ack_outcome(
                    delivery_id, status="failed", error_class=type(exc).__name__
                )
            else:
                await self._record_ack_outcome(
                    delivery_id, status="delivered", telegram_message_id=message_id
                )
            sent += 1
        return sent

    async def run_forever(self, interval_seconds: float) -> None:
        """Poll recoverable work; errors do not terminate the lifecycle task."""
        while True:
            try:
                processed = await self.run_once()
                if self._on_cycle is not None:
                    self._on_cycle(processed)
            except Exception:
                logger.exception("Interaction processor cycle failed")
            await asyncio.sleep(interval_seconds)

    async def _process_chat_queue(self, interactions: Sequence[TelegramInteraction]) -> int:
        processed = 0
        for interaction in interactions:
            if await self._process_interaction(interaction):
                processed += 1
        return processed

    async def _process_interaction(self, interaction: TelegramInteraction) -> bool:
        chat_key = interaction.chat_id if interaction.chat_id is not None else -1
        user_key = interaction.telegram_user_id if interaction.telegram_user_id is not None else -1
        chat_lock = self._chat_locks.setdefault(chat_key, asyncio.Lock())
        user_lock = self._user_locks.setdefault(user_key, asyncio.Lock())
        queued_at = time.perf_counter()

        async with chat_lock, user_lock, self._global_semaphore:
            get_telemetry().duration_ms(
                "ancora.interaction.queue.wait",
                (time.perf_counter() - queued_at) * 1000,
                attributes={"ancora.queue.status": "acquired"},
            )
            if interaction.status is InteractionStatus.ACCEPTED:
                return await self._run_agent(interaction)
            if interaction.status is InteractionStatus.RESPONSE_READY:
                return await self._deliver_response(interaction)
        return False

    async def _run_agent(
        self,
        interaction: TelegramInteraction,
        *,
        voice_text: str | None = None,
        prepared_context: ExecutionContext | None = None,
    ) -> bool:
        if interaction.chat_id is None or interaction.telegram_user_id is None:
            await self._mark_terminal(
                interaction.id,
                InteractionStatus.FAILED_CONTROLLED,
                error_class="InteractionValidationError",
                error_detail_code="missing_chat_or_user_identity",
            )
            return True
        if interaction.payload_ciphertext is None:
            await self._mark_terminal(
                interaction.id,
                InteractionStatus.FAILED_CONTROLLED,
                error_class="PayloadUnavailableError",
                error_detail_code="accepted_payload_missing",
            )
            return True

        try:
            payload = self._payload_cipher.decrypt(interaction.payload_ciphertext)
        except ValueError:
            await self._mark_terminal(
                interaction.id,
                InteractionStatus.FAILED_CONTROLLED,
                error_class="PayloadDecodeError",
                error_detail_code="payload_unusable",
            )
            return True
        if interaction.update_type == "callback_query":
            # Channel receipt is independent from authorization/execution.
            # Never parse callback data as a command, voice, upload or LLM input.
            return await self._process_callback(interaction, payload)
        try:
            input_text = payload.get("text")
            attachments = tuple(
                TelegramAttachment.model_validate(item) for item in payload.get("attachments", [])
            )
            voices = tuple(item for item in attachments if item.kind == "voice")
            if voices and voice_text is None:
                return await self._prepare_voice(interaction, voices[0], payload)
            if voice_text is not None:
                input_text = voice_text
                attachments = ()
            if (not isinstance(input_text, str) or not input_text.strip()) and attachments:
                input_text = (
                    "He adjuntado un documento. Archívalo y analízalo usando analyze_document."
                )
            if not isinstance(input_text, str) or not input_text.strip():
                raise ValueError("normalized Telegram update has no processable text")
        except ValueError:
            await self._mark_terminal(
                interaction.id,
                InteractionStatus.FAILED_CONTROLLED,
                error_class="PayloadDecodeError",
                error_detail_code="payload_unusable",
            )
            return True

        run_id = prepared_context.agno_run_id if prepared_context else str(uuid4())
        if self._governed_consent and voice_text is None:
            consent_reply = await self._handle_consent_input(interaction, input_text)
            if consent_reply is not None:
                return await self._reply_deterministically(interaction, consent_reply)
        command = (
            parse_telegram_command(input_text, bot_username=self._bot_username)
            if not attachments and voice_text is None
            else None
        )
        if command is not None:
            # BL-28: commands are control input, never model input.
            return await self._handle_command(interaction, command)

        session_id = (
            prepared_context.agno_session_id
            if prepared_context
            else await self._conversation_session_id(interaction.chat_id)
        )
        claimed = await self._claim_agent(interaction.id, run_id, session_id)
        if claimed is None:
            return False

        compaction_summary, reduced_history_runs = await self._maybe_compact_context(session_id)

        attributes = {
            "ancora.correlation_id": str(interaction.correlation_id),
            "ancora.interaction_id": str(interaction.id),
            "telegram.update_id": interaction.telegram_update_id,
            "telegram.message_id": interaction.telegram_message_id,
            "agno.run_id": run_id,
            "agno.session_id": session_id,
        }

        typing_task = asyncio.create_task(
            self._refresh_typing(interaction.chat_id),
            name=f"telegram-typing-{interaction.id}",
        )
        if attachments and self._fast_ack_enabled:
            await self._send_fast_ack(interaction)
        started = time.perf_counter()
        with (
            log_context_scope(attributes),
            get_telemetry().span("interaction.process", attributes) as span,
        ):
            try:
                media: tuple[ResolvedTelegramMedia, ...] = ()
                if attachments:
                    if self._media_resolver is None:
                        raise AttachmentResolutionError("attachment_resolver_unavailable")
                    resolved_media = [
                        await self._media_resolver.resolve(attachment) for attachment in attachments
                    ]
                    media = tuple(resolved_media)
                content = await self._agent_runner.run(
                    input_text,
                    user_id=str(interaction.telegram_user_id),
                    session_id=session_id,
                    run_id=run_id,
                    correlation_id=interaction.correlation_id,
                    telegram_update_id=interaction.telegram_update_id,
                    telegram_message_id=interaction.telegram_message_id,
                    media=media,
                    provenance=self._provenance(interaction),
                    compaction_summary=compaction_summary,
                    reduced_history_runs=reduced_history_runs,
                    **({"execution_context": prepared_context} if prepared_context else {}),
                )
                content = await self._append_proposal_blocks(interaction, content)
                if not content.strip():
                    await self._mark_terminal(
                        interaction.id,
                        InteractionStatus.FAILED_CONTROLLED,
                        error_class="EmptyAgentResponse",
                        error_detail_code="agent_returned_empty_content",
                    )
                    return True
                encrypted = self._payload_cipher.encrypt({"content": content})
                chunks = split_telegram_message(content)
                response = await self._persist_response(
                    interaction.id,
                    content_ciphertext=encrypted.ciphertext,
                    content_key_version=encrypted.key_version,
                    content_length=len(content),
                    chunk_count=len(chunks),
                )
                if response is None:
                    # The run already happened; never run it again if persistence raced or failed.
                    await self._mark_terminal(
                        interaction.id,
                        InteractionStatus.FAILED_AMBIGUOUS,
                        error_class="OutboxPersistenceError",
                        error_detail_code="response_ready_transition_missing",
                    )
                    return True
            except asyncio.CancelledError:
                raise
            except AttachmentResolutionError as exc:
                get_telemetry().mark_error(span, type(exc).__name__)
                await self._mark_terminal(
                    interaction.id,
                    InteractionStatus.FAILED_CONTROLLED,
                    error_class="AttachmentResolutionError",
                    error_detail_code=exc.code,
                )
                return True
            except CostGovernanceError as exc:
                # The spend ceiling was evaluated before any inference: the
                # failure is deterministic, so it is controlled — never replayed.
                get_telemetry().mark_error(span, type(exc).__name__)
                get_telemetry().counter(
                    "ancora.cost_governance.hard_stop",
                    attributes={"ancora.cost.limit": exc.limit},
                )
                await self._mark_terminal(
                    interaction.id,
                    InteractionStatus.FAILED_CONTROLLED,
                    error_class="CostGovernanceError",
                    error_detail_code=exc.limit,
                )
                return True
            except EmergencyStopActiveError as exc:
                # A manual operator stop is deterministic and known in advance
                # (checked before — or, mid-run, before — any model call): the
                # failure is controlled, never replayed (BL-44/specs/031).
                get_telemetry().mark_error(span, type(exc).__name__)
                get_telemetry().counter("ancora.emergency_stop.blocked")
                await self._mark_terminal(
                    interaction.id,
                    InteractionStatus.FAILED_CONTROLLED,
                    error_class="EmergencyStopActiveError",
                    error_detail_code="emergency_stop_active",
                )
                return True
            except ExecutionBudgetExceededError as exc:
                get_telemetry().mark_error(span, type(exc).__name__)
                get_telemetry().counter(
                    "ancora.execution_budget.exceeded",
                    attributes={"ancora.budget.limit": exc.limit},
                )
                await self._mark_terminal(
                    interaction.id,
                    InteractionStatus.FAILED_AMBIGUOUS,
                    error_class="ExecutionBudgetExceededError",
                    error_detail_code=exc.limit,
                )
                return True
            except InvalidPresentationOutputError:
                get_telemetry().mark_error(span, "InvalidPresentationOutputError")
                await self._mark_terminal(
                    interaction.id,
                    InteractionStatus.FAILED_AMBIGUOUS,
                    error_class="InvalidPresentationOutputError",
                    error_detail_code="invalid_terminal_presentation",
                )
                await self._send_failure_notice(interaction)
                return True
            except Exception:
                get_telemetry().mark_error(span, "AgentRunError")
                await self._mark_terminal(
                    interaction.id,
                    InteractionStatus.FAILED_AMBIGUOUS,
                    error_class="AgentRunError",
                    error_detail_code="agent_run_failed_after_claim",
                )
                return True
            finally:
                get_telemetry().duration_ms(
                    "ancora.interaction.process.duration",
                    (time.perf_counter() - started) * 1000,
                    attributes={"ancora.status": "completed"},
                )
                typing_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await typing_task

        response_ready = interaction.model_copy(update={"status": InteractionStatus.RESPONSE_READY})
        return await self._deliver_response(response_ready)

    async def _prepare_voice(
        self,
        interaction: TelegramInteraction,
        attachment: TelegramAttachment,
        payload: dict[str, Any],
    ) -> bool:
        service = self._voice_preparation
        if not self._voice_enabled or service is None:
            return await self._reply_deterministically(
                interaction,
                "Las notas de voz todavía no están habilitadas. Puedes escribir tu mensaje.",
            )
        try:
            if interaction.chat_id is None or attachment.duration_seconds is None:
                raise VoicePreparationError("voice_empty_or_invalid")
            if (
                interaction.update_type != "message"
                or payload.get("voice_message_kind") != "original"
                or payload.get("text")
                or len(payload.get("attachments", [])) != 1
            ):
                raise VoicePreparationError("voice_origin_not_allowed")
            reference = VoiceReference(
                file_id=attachment.file_id,
                duration_seconds=attachment.duration_seconds,
                size_bytes=attachment.size_bytes,
                mime_type=attachment.mime_type,
            )
            if reference.duration_seconds > service.policy.max_duration_seconds:
                raise VoicePreparationError("voice_duration_exceeded")
            service.policy.validate_download_size(reference.size_bytes or 0)
            async with service.exclusive(interaction.id) as acquired:
                if not acquired:
                    return False
                prepare_context = getattr(self._agent_runner, "prepare_execution_context", None)
                if prepare_context is None:
                    raise VoicePreparationError("stt_route_unavailable")
                context = await prepare_context(
                    session_id=await self._conversation_session_id(interaction.chat_id),
                    run_id=str(uuid4()),
                    correlation_id=interaction.correlation_id,
                    telegram_update_id=interaction.telegram_update_id,
                    telegram_message_id=interaction.telegram_message_id,
                    provenance=self._provenance(interaction),
                )
                text = await service.prepare(interaction, attachment, context=context)
                if text is None:
                    return False
                if parse_voice_consent_intent(text) is not None:
                    reply = await self._handle_voice_consent(
                        interaction, text, context.agno_session_id
                    )
                    return await self._reply_deterministically(interaction, reply)
                return await self._run_agent(interaction, voice_text=text, prepared_context=context)
        except asyncio.CancelledError:
            await self._mark_terminal(
                interaction.id,
                InteractionStatus.FAILED_AMBIGUOUS,
                error_class="VoicePreparationError",
                error_detail_code="voice_cancelled",
            )
            raise
        except Exception as exc:
            ambiguous = isinstance(exc, VoicePreparationError) and exc.ambiguous
            code = (
                exc.code if isinstance(exc, VoicePreparationError) else "voice_preparation_failed"
            )
            await self._mark_terminal(
                interaction.id,
                InteractionStatus.FAILED_AMBIGUOUS
                if ambiguous
                else InteractionStatus.FAILED_CONTROLLED,
                error_class="VoicePreparationError",
                error_detail_code=code,
            )
            # Controlled and ambiguous failures both notify the user; neither
            # retries STT nor starts the Agent (the notice is a fixed constant).
            return await self._reply_deterministically(
                interaction,
                VOICE_NOT_UNDERSTOOD_REPLY,
                voice_failure_notice=True,
            )

    def _provenance(self, interaction: TelegramInteraction) -> InteractionProvenance | None:
        """Trusted origin for ``propose_*`` tools; ``None`` while the rollout is off."""
        if not self._governed_consent or interaction.chat_id is None:
            return None
        return InteractionProvenance(
            interaction_id=interaction.id,
            bot_id=interaction.bot_id,
            chat_id=interaction.chat_id,
        )

    async def _append_proposal_blocks(
        self, interaction: TelegramInteraction, content: str | AgentReply
    ) -> str:
        """Replace proposal narration, preserving independent answers (BL-48).

        The block is generated from the stored payload and user-scoped
        canonical target title, never from the model's wording (BL-49).
        Unbacked proposal narration is always discarded (specs/023 T4.4).
        """
        # Proposal narration is never evidence that a proposal exists. Only
        # stored rows below may produce proposal text or confirmation controls.
        text = (
            content.answer.strip() or "No se ha presentado ninguna propuesta para confirmar."
            if isinstance(content, AgentReply)
            else content
        )
        if not self._governed_consent:
            return text
        session = await self._session_factory()
        try:
            created = await ActionProposalsRepository(session).list_created_in_interaction(
                interaction.id, user_id=str(interaction.telegram_user_id)
            )
            if not created:
                return text
            if not isinstance(content, AgentReply):
                # Never deduce proposal narration from free-form prose.
                raise ValueError("Proposal presentation requires a partitioned Agent reply")
            blocks: list[str] = []
            for row in created:
                reminder_title = None
                if row["tool_name"] == "snooze_reminder":
                    raw_id = row["payload"].get("reminder_id")
                    try:
                        reminder_id = UUID(raw_id) if isinstance(raw_id, str) else None
                    except ValueError:
                        reminder_id = None
                    if reminder_id is not None:
                        reminder = await RemindersRepository(session).get_by_id(
                            str(interaction.telegram_user_id), reminder_id
                        )
                        if reminder is not None:
                            reminder_title = reminder.title
                blocks.append(
                    render_proposal_block(
                        row["id"], row["tool_name"], row["payload"], reminder_title=reminder_title,
                        timezone=resolve_user_timezone(
                            UserContext(user_id=str(interaction.telegram_user_id))
                        ),
                    )
                )
            return "\n\n".join(part for part in (content.answer.strip(), *blocks) if part)
        finally:
            await session.close()

    async def _mark_proposals_presented(
        self, interaction: TelegramInteraction, response_id: UUID
    ) -> None:
        """Open the consent window only after Telegram confirmed the delivery.

        Re-queries by interaction instead of trusting the earlier button list:
        a crash between persisting and delivering must not open a window for a
        proposal the user never actually saw delivered.
        """
        if interaction.chat_id is None or interaction.telegram_user_id is None:
            return  # pragma: no cover - _run_agent already validated identity
        principal = ConsentPrincipal(
            user_id=str(interaction.telegram_user_id),
            bot_id=interaction.bot_id,
            chat_id=interaction.chat_id,
        )
        session = await self._session_factory()
        try:
            repo = ActionProposalsRepository(session)
            created = await repo.list_created_in_interaction(
                interaction.id, user_id=principal.user_id
            )
            if created:
                await repo.mark_presented(
                    [row["id"] for row in created],
                    principal=principal,
                    response_id=response_id,
                    presented_at=datetime.now(tz=UTC),
                )
                await session.commit()
        finally:
            await session.close()

    async def _pending_proposal_buttons(
        self, interaction: TelegramInteraction
    ) -> tuple[tuple[ConsentButton, ConsentButton], ...]:
        """Sí/No rows for proposals this run just created (specs/023 T4.3-T4.4).

        Returns nothing while the rollout is off, so delivery is byte-for-byte
        unchanged until T4.5 can act on a confirmed claim.
        """
        if not self._governed_consent:
            return ()
        session = await self._session_factory()
        try:
            created = await ActionProposalsRepository(session).list_created_in_interaction(
                interaction.id, user_id=str(interaction.telegram_user_id)
            )
        finally:
            await session.close()
        return tuple(consent_buttons(row["id"]) for row in created)

    async def _refresh_typing(self, chat_id: int) -> None:
        """Keep Telegram's non-content typing indicator alive during an Agent run."""
        while True:
            try:
                await self._sender.send_typing(chat_id)
            except Exception:
                logger.debug("Telegram typing refresh failed", exc_info=True)
            await asyncio.sleep(self._typing_refresh_seconds)

    async def _send_fast_ack(self, interaction: TelegramInteraction) -> None:
        """Best-effort early acknowledgement for attachment-bearing interactions (BL-32).

        Lives entirely outside the main response's outbox state machine: it
        never reads or writes ``telegram_interactions.status``, so it cannot
        interfere with ``agent_started``/``response_ready``/at-most-once
        semantics. A failure here — persistence or send — is logged and
        swallowed; it never blocks, delays or fails the main Agent run, and
        is never retried on a later cycle (no recovery scan exists for it,
        unlike the final response).
        """
        try:
            encrypted = self._payload_cipher.encrypt({"content": DOCUMENT_RECEIVED_ACK})
            session = await self._session_factory()
            try:
                delivery_id = await TelegramInteractionsRepository(session).create_ack_response(
                    interaction.id,
                    content_ciphertext=encrypted.ciphertext,
                    content_key_version=encrypted.key_version,
                    content_length=len(DOCUMENT_RECEIVED_ACK),
                )
            finally:
                await session.close()
            if delivery_id is None:
                # Already created on a prior attempt for this interaction —
                # never resend (idempotent across reprocessing).
                return
            assert interaction.chat_id is not None  # validated by the caller
            try:
                message_id = await self._sender.send_text(
                    interaction.chat_id, DOCUMENT_RECEIVED_ACK
                )
            except Exception as exc:
                await self._record_ack_outcome(
                    delivery_id, status="failed", error_class=type(exc).__name__
                )
                return
            await self._record_ack_outcome(
                delivery_id, status="delivered", telegram_message_id=message_id
            )
        except Exception:
            logger.warning("Fast-ack failed for interaction %s", interaction.id, exc_info=True)

    async def _send_failure_notice(self, interaction: TelegramInteraction) -> None:
        """Best-effort notice after a terminal presentation failure.

        The interaction is already ``failed_ambiguous``. This secondary outbox
        never changes that state, retries the Agent or claims an operation result.
        """
        if interaction.chat_id is None:  # pragma: no cover - validated before claim
            return
        try:
            encrypted = self._payload_cipher.encrypt(
                {"content": AGENT_PRESENTATION_FAILURE_NOTICE}
            )
            session = await self._session_factory()
            try:
                delivery_id = await TelegramInteractionsRepository(
                    session
                ).create_failure_notice_response(
                    interaction.id,
                    content_ciphertext=encrypted.ciphertext,
                    content_key_version=encrypted.key_version,
                    content_length=len(AGENT_PRESENTATION_FAILURE_NOTICE),
                )
            finally:
                await session.close()
            if delivery_id is None:
                return
            try:
                message_id = await self._sender.send_text(
                    interaction.chat_id, AGENT_PRESENTATION_FAILURE_NOTICE
                )
            except Exception as exc:
                await self._record_ack_outcome(
                    delivery_id, status="failed", error_class=type(exc).__name__
                )
                return
            await self._record_ack_outcome(
                delivery_id, status="delivered", telegram_message_id=message_id
            )
        except Exception:
            logger.warning(
                "Agent presentation failure notice could not be delivered",
                exc_info=True,
            )

    async def _record_ack_outcome(
        self,
        delivery_id: UUID,
        *,
        status: str,
        telegram_message_id: int | None = None,
        error_class: str | None = None,
    ) -> None:
        session = await self._session_factory()
        try:
            await TelegramInteractionsRepository(session).mark_ack_delivery_outcome(
                delivery_id,
                status=status,
                telegram_message_id=telegram_message_id,
                error_class=error_class,
            )
        finally:
            await session.close()

    async def _handle_command(
        self,
        interaction: TelegramInteraction,
        command: TelegramCommand,
    ) -> bool:
        """Answer a bot command deterministically, without any Agent execution.

        The reply travels through the same durable outbox as an Agent response
        (chunking, delivery state, ambiguity rules), so delivery semantics stay
        identical while the model never sees the command nor the chat history.
        """
        handling = handle_telegram_command(command, pilot_notice_url=self._pilot_notice_url)
        chat_id = interaction.chat_id
        if chat_id is None:  # pragma: no cover - _run_agent validates identity first
            await self._mark_terminal(
                interaction.id,
                InteractionStatus.FAILED_CONTROLLED,
                error_class="InteractionValidationError",
                error_detail_code="missing_chat_identity_for_command",
            )
            return True
        new_session_id: str | None = None
        if handling.resets_session:
            new_session_id = next_session_id(
                chat_id,
                await self._stored_session_id(chat_id),
            )
            if self._governed_consent and interaction.telegram_user_id is not None:
                await self._discard_pending_proposals_for_chat(interaction)
        encrypted = self._payload_cipher.encrypt({"content": handling.reply_text})
        chunks = split_telegram_message(handling.reply_text)
        response = await self._persist_command_reply(
            interaction.id,
            agno_session_id=new_session_id,
            content_ciphertext=encrypted.ciphertext,
            content_key_version=encrypted.key_version,
            content_length=len(handling.reply_text),
            chunk_count=len(chunks),
        )
        get_telemetry().counter(
            "ancora.telegram.commands",
            attributes={
                "ancora.command": telemetry_label(command),
                "ancora.status": "completed" if response is not None else "duplicate",
            },
        )
        if response is None:
            # A concurrent claim already answered this update: never reply twice.
            return False
        return await self._deliver_response(
            interaction.model_copy(update={"status": InteractionStatus.RESPONSE_READY})
        )

    async def _reply_deterministically(
        self,
        interaction: TelegramInteraction,
        reply_text: str,
        *,
        voice_failure_notice: bool = False,
    ) -> bool:
        """Answer a confirmation/discard outcome without any Agent execution.

        Same durable outbox as a command reply (specs/023 T4.3): the model
        never sees the callback or the «Sí»/«No» text.
        """
        encrypted = self._payload_cipher.encrypt({"content": reply_text})
        chunks = split_telegram_message(reply_text)
        response = await self._persist_command_reply(
            interaction.id,
            agno_session_id=None,
            content_ciphertext=encrypted.ciphertext,
            content_key_version=encrypted.key_version,
            content_length=len(reply_text),
            chunk_count=len(chunks),
            **({"voice_failure_notice": True} if voice_failure_notice else {}),
        )
        if response is None:
            # A concurrent claim already answered this update: never reply twice.
            return False
        return await self._deliver_response(
            interaction.model_copy(update={"status": InteractionStatus.RESPONSE_READY})
        )

    async def _discard_pending_proposals_for_chat(self, interaction: TelegramInteraction) -> None:
        """Invalidate every pending proposal of this chat on ``/new`` (consent-design).

        ``/new`` does not revive or renew proposals: resetting the conversation
        must not leave a stale proposal confirmable from a thread the user no
        longer sees. Best-effort — a failure here must not block the ``/new``
        reply itself (the window still expires on its own after 15 minutes).
        """
        if interaction.chat_id is None or interaction.telegram_user_id is None:
            return  # pragma: no cover - caller already checked
        principal = ConsentPrincipal(
            user_id=str(interaction.telegram_user_id),
            bot_id=interaction.bot_id,
            chat_id=interaction.chat_id,
        )
        session = await self._session_factory()
        try:
            await ActionProposalsRepository(session).discard_pending_for_chat(principal)
            await session.commit()
        except Exception:
            logger.warning("Failed to discard pending proposals on /new", exc_info=True)
        finally:
            await session.close()

    async def _process_callback(
        self, interaction: TelegramInteraction, payload: dict[str, Any]
    ) -> bool:
        """Acknowledge an admitted button, then independently resolve its consent.

        No success notice is attached to the acknowledgement. Best-effort failure
        cannot authorize, roll back, retry or replay the canonical action. The
        durable ledger suppresses duplicate admission; no ack retry is scheduled.
        Old encrypted payloads without an id still use the Core consent path.
        """
        callback_id = bounded_callback_query_id(payload.get("callback_query_id"))
        if callback_id is not None:
            try:
                await asyncio.wait_for(
                    self._sender.answer_callback_query(callback_id),
                    timeout=CALLBACK_ACK_TIMEOUT_SECONDS,
                )
            except Exception as exc:
                # Never log the identifier, Bot API URL/token, exception text or
                # response body; none belong in operational telemetry.
                logger.warning(
                    "Callback acknowledgement failed (error_class=%s)", type(exc).__name__
                )
        if not self._governed_consent:
            reply = CALLBACK_DISABLED_REPLY
        else:
            raw = payload.get("text")
            callback = parse_consent_callback(raw if isinstance(raw, str) else None)
            if callback is None:
                reply = CALLBACK_INVALID_REPLY
            else:
                assert interaction.telegram_user_id is not None and interaction.chat_id is not None
                principal = ConsentPrincipal(
                    user_id=str(interaction.telegram_user_id),
                    bot_id=interaction.bot_id,
                    chat_id=interaction.chat_id,
                )
                reply = await self._handle_consent_callback(interaction, principal, callback)
        return await self._reply_deterministically(interaction, reply)

    async def _handle_consent_input(
        self, interaction: TelegramInteraction, input_text: str
    ) -> str | None:
        """Resolve a Sí/No button or written «Sí» before any Agent execution.

        Returns the deterministic reply text, or ``None`` if ``input_text``
        is not consent input (the caller then falls through to commands/Agent
        as usual). Button data is only an identifier here: every outcome is
        re-validated by ``ActionProposalsRepository`` against principal, bot,
        chat, window and payload hash.
        """
        if interaction.chat_id is None or interaction.telegram_user_id is None:
            return None  # pragma: no cover - _run_agent validates identity first
        principal = ConsentPrincipal(
            user_id=str(interaction.telegram_user_id),
            bot_id=interaction.bot_id,
            chat_id=interaction.chat_id,
        )

        callback = parse_consent_callback(input_text)
        if callback is not None:
            return await self._handle_consent_callback(interaction, principal, callback)

        intent = parse_consent_intent(input_text)
        if intent is None:
            return None
        if intent.proposal_id is not None:
            return await self._claim_and_report(interaction, principal, intent.proposal_id)
        return await self._resolve_bare_confirmation(interaction, principal)

    async def _handle_consent_callback(
        self,
        interaction: TelegramInteraction,
        principal: ConsentPrincipal,
        callback: ConsentCallback,
    ) -> str:
        session = await self._session_factory()
        try:
            repo = ActionProposalsRepository(session)
            if callback.action is ConsentAction.DISCARD:
                discarded = await repo.discard_proposal(callback.proposal_id, principal=principal)
                await session.commit()
                return (
                    "❌ Propuesta descartada."
                    if discarded
                    else "Esa propuesta ya no está pendiente."
                )
            result = await repo.claim_confirmation(
                callback.proposal_id,
                principal=principal,
                confirming_interaction_id=interaction.id,
            )
            await session.commit()
        finally:
            await session.close()
        if not result.ok:
            return self._consent_rejection_reply(result.rejection)
        return await self._execute_claimed(result, user_id=principal.user_id)

    async def _claim_and_report(
        self,
        interaction: TelegramInteraction,
        principal: ConsentPrincipal,
        proposal_id: UUID,
    ) -> str:
        """Written «Sí <UUID>» — same claim path as the confirm button."""
        session = await self._session_factory()
        try:
            result = await ActionProposalsRepository(session).claim_confirmation(
                proposal_id, principal=principal, confirming_interaction_id=interaction.id
            )
            await session.commit()
        finally:
            await session.close()
        if not result.ok:
            return self._consent_rejection_reply(result.rejection)
        return await self._execute_claimed(result, user_id=principal.user_id)

    async def _resolve_bare_confirmation(
        self, interaction: TelegramInteraction, principal: ConsentPrincipal
    ) -> str:
        """Written «Sí» alone: exactly one confirmable proposal, or ask to pick."""
        session = await self._session_factory()
        try:
            repo = ActionProposalsRepository(session)
            confirmable = await repo.list_confirmable(principal)
            result = None
            if len(confirmable) == 1:
                result = await repo.claim_confirmation(
                    confirmable[0],
                    principal=principal,
                    confirming_interaction_id=interaction.id,
                )
                await session.commit()
        finally:
            await session.close()
        if result is None:
            if not confirmable:
                return "No tienes ninguna propuesta pendiente de confirmar."
            ids = "\n".join(f"- `{proposal_id}`" for proposal_id in confirmable)
            return f"Tienes varias propuestas pendientes. Responde «Sí <ID>»:\n{ids}"
        if not result.ok:
            return self._consent_rejection_reply(result.rejection)
        return await self._execute_claimed(result, user_id=principal.user_id)

    @staticmethod
    def _consent_rejection_reply(rejection: ConsentRejection | None) -> str:
        if rejection in (ConsentRejection.NOT_FOUND, ConsentRejection.LEGACY_PROPOSAL):
            return "No encontré esa propuesta. Pídemela de nuevo."
        if rejection is ConsentRejection.EXPIRED:
            return "Esa propuesta ya caducó (15 min). Pídemela de nuevo."
        if rejection is ConsentRejection.INTERACTION_ALREADY_USED:
            return "Ya has confirmado otra propuesta con este mensaje."
        return "Esa propuesta ya no está pendiente de confirmación."

    async def _handle_voice_consent(
        self, interaction: TelegramInteraction, text: str, session_id: str
    ) -> str:
        from src.domain.actions.executor import ProposalExecutor
        from src.domain.speech.consent import VoiceConsentIntent
        from src.repositories.voice_preparations import VoicePreparationsRepository

        if (
            not self._governed_consent
            or interaction.telegram_user_id is None
            or interaction.chat_id is None
            or parse_voice_consent_intent(text) is None
        ):
            return (
                "La confirmación por voz aún no está habilitada. "
                "No se ha ejecutado ninguna operación."
            )
        # Check the ORIGINAL encrypted payload as well as the transcript from the
        # owner-controlled preparation. Neither free text nor history can consent.
        session = await self._session_factory()
        try:
            preparation = await VoicePreparationsRepository(session).get(
                interaction.id, interaction.telegram_user_id
            )
            if preparation is None or preparation.transcript_ciphertext is None:
                return "No pude verificar la confirmación de voz."
            from src.domain.speech.preparation import SpeechTranscriptCipher

            transcript = SpeechTranscriptCipher(self._payload_cipher).decrypt(
                preparation.transcript_ciphertext
            )
            original = self._payload_cipher.decrypt(interaction.payload_ciphertext or b"")
            if (
                transcript.text != text
                or transcript.call_id != preparation.call_id
                or original.get("voice_message_kind") != "original"
                or original.get("text")
                or len(original.get("attachments", [])) != 1
                or original["attachments"][0].get("kind") != "voice"
            ):
                return "No pude verificar la confirmación de voz."
            principal = ConsentPrincipal(
                user_id=str(interaction.telegram_user_id),
                bot_id=interaction.bot_id,
                chat_id=interaction.chat_id,
            )
            result, code = await ActionProposalsRepository(session).resolve_voice_consent(
                principal=principal,
                interaction_id=interaction.id,
                session_id=session_id,
                discard=parse_voice_consent_intent(text) is VoiceConsentIntent.DISCARD,
                supported_tools=ProposalExecutor.SUPPORTED,
            )
            await session.commit()
        finally:
            await session.close()
        if code == "voice_executor_unavailable":
            return (
                "Esta operación todavía no tiene ejecutor determinista. "
                "La propuesta sigue pendiente."
            )
        if result is None:
            return (
                "No hay una única propuesta vigente presentada antes de esta nota de voz. "
                "No se ha ejecutado ninguna operación."
            )
        if not result.ok:
            return self._consent_rejection_reply(result.rejection)
        if parse_voice_consent_intent(text) is VoiceConsentIntent.DISCARD:
            return "❌ Propuesta descartada."
        return await self._execute_claimed(result, user_id=principal.user_id)

    async def _execute_claimed(self, result: ConsentClaimResult, *, user_id: str) -> str:
        """Execute a Core-verified claim identically for voice, text and buttons."""
        assert result.claimed is not None
        storage = None
        if result.claimed.tool_name == "delete_document":
            from src.config import Settings
            from src.storage.factory import create_storage

            storage = create_storage(Settings())
        return await ProposalExecutor(self._session_factory, storage=storage).execute(
            result.claimed, user_id=user_id
        )

    async def _stored_session_id(self, chat_id: int) -> str | None:
        """Return the session the ledger last recorded for this chat, if any."""
        session = await self._session_factory()
        try:
            stored = await TelegramInteractionsRepository(session).current_session_id(chat_id)
        finally:
            await session.close()
        return stored if isinstance(stored, str) and stored.strip() else None

    async def _conversation_session_id(self, chat_id: int) -> str:
        """Resolve the chat's current conversation session from the ledger.

        ``/new`` stores the generation it opened on its own interaction row, so
        the ledger is the single source of truth: a restart cannot resurrect an
        abandoned conversation (BL-28).
        """
        return await self._stored_session_id(chat_id) or default_session_id(chat_id)

    async def _deliver_response(self, interaction: TelegramInteraction) -> bool:
        if interaction.chat_id is None:
            await self._mark_terminal(
                interaction.id,
                InteractionStatus.FAILED_CONTROLLED,
                error_class="InteractionValidationError",
                error_detail_code="missing_chat_identity_for_delivery",
            )
            return True
        response = await self._claim_delivery(interaction.id)
        if response is None:
            return False
        if response.content_ciphertext is None:
            await self._mark_terminal(
                interaction.id,
                InteractionStatus.FAILED_AMBIGUOUS,
                error_class="ResponsePayloadUnavailable",
                error_detail_code="logical_response_ciphertext_missing",
            )
            return True
        try:
            decrypted = self._payload_cipher.decrypt(response.content_ciphertext)
            content = decrypted.get("content")
            if not isinstance(content, str):
                raise ValueError("logical response content is invalid")
            chunks = split_telegram_message(content)
        except ValueError:
            await self._mark_terminal(
                interaction.id,
                InteractionStatus.FAILED_AMBIGUOUS,
                error_class="ResponsePayloadDecodeError",
                error_detail_code="logical_response_unusable",
            )
            return True

        deliveries = await self._list_deliveries(response.id)
        proposal_buttons = await self._pending_proposal_buttons(interaction)
        last_chunk_index = len(deliveries) - 1
        for delivery in deliveries:
            if delivery.status == "completed":
                continue
            claimed = await self._claim_chunk(response.id, delivery.chunk_index)
            if claimed is None:
                # A non-pending chunk makes retry semantics uncertain. Do not resend.
                await self._mark_terminal(
                    interaction.id,
                    InteractionStatus.FAILED_AMBIGUOUS,
                    error_class="DeliveryStateConflict",
                    error_detail_code="response_chunk_not_pending",
                )
                return True
            try:
                attributes = {
                    "ancora.correlation_id": str(interaction.correlation_id),
                    "ancora.interaction_id": str(interaction.id),
                    "telegram.update_id": interaction.telegram_update_id,
                }
                started = time.perf_counter()
                with (
                    log_context_scope(attributes),
                    get_telemetry().span("telegram.response.send", attributes) as span,
                ):
                    try:
                        buttons_for_chunk = (
                            proposal_buttons
                            if claimed.chunk_index == last_chunk_index and proposal_buttons
                            else None
                        )
                        message_id = (
                            await self._sender.send_text(
                                interaction.chat_id,
                                chunks[claimed.chunk_index],
                                button_rows=buttons_for_chunk,
                            )
                            if buttons_for_chunk is not None
                            else await self._sender.send_text(
                                interaction.chat_id, chunks[claimed.chunk_index]
                            )
                        )
                        await self._mark_chunk_delivered(claimed.id, message_id)
                        if claimed.chunk_index == last_chunk_index and proposal_buttons:
                            await self._mark_proposals_presented(interaction, response.id)
                        get_telemetry().counter(
                            "ancora.telegram.deliveries",
                            attributes={"ancora.delivery.status": "completed"},
                        )
                    finally:
                        get_telemetry().duration_ms(
                            "ancora.telegram.delivery.duration",
                            (time.perf_counter() - started) * 1000,
                            attributes={"ancora.delivery.status": "completed"},
                        )
            except asyncio.CancelledError:
                raise
            except TelegramSendError as exc:
                get_telemetry().mark_error(span, type(exc).__name__)
                get_telemetry().counter(
                    "ancora.telegram.deliveries",
                    attributes={
                        "ancora.delivery.status": "error",
                        "error.type": type(exc).__name__,
                    },
                )
                await self._fail_delivery(
                    interaction.id,
                    response.id,
                    claimed.id,
                    InteractionStatus.FAILED_DEFINITIVE
                    if exc.definitive
                    else InteractionStatus.FAILED_AMBIGUOUS,
                    type(exc).__name__,
                )
                return True
            except Exception:
                get_telemetry().mark_error(span, "TelegramSendUnknownError")
                get_telemetry().counter(
                    "ancora.telegram.deliveries",
                    attributes={
                        "ancora.delivery.status": "error",
                        "error.type": "TelegramSendUnknownError",
                    },
                )
                await self._fail_delivery(
                    interaction.id,
                    response.id,
                    claimed.id,
                    InteractionStatus.FAILED_AMBIGUOUS,
                    "TelegramSendUnknownError",
                )
                return True

        finalized = await self._finalize_delivery(interaction.id, response.id)
        if finalized and self._on_interaction_completed is not None:
            self._on_interaction_completed()
        return finalized

    async def _claim_agent(
        self, interaction_id: UUID, run_id: str, session_id: str
    ) -> TelegramInteraction | None:
        session = await self._session_factory()
        try:
            return await TelegramInteractionsRepository(session).claim_agent_start_with_run_id(
                interaction_id, run_id, session_id
            )
        finally:
            await session.close()

    async def _maybe_compact_context(self, session_id: str) -> tuple[str | None, int | None]:
        """Cheap gate first; the expensive read only runs once it's crossed.

        BL-34, 2026-10-12: with the flag off (default), this returns
        immediately — zero queries, identical behaviour to before this
        feature existed. A compaction failure degrades to ``(None, None)``,
        never raises: the caller must still run with today's behaviour.
        """
        if not self._context_compaction_enabled or self._summarizer is None:
            return None, None
        session = await self._session_factory()
        try:
            tokens = await LlmUsageRepository(session).sum_session_tokens(session_id)
            if tokens < self._context_compaction_token_threshold:
                return None, None
            rows = await TelegramInteractionsRepository(session).list_session_exchanges(session_id)
        finally:
            await session.close()
        compact_count = oldest_fraction_count(len(rows), self._context_compaction_ratio)
        if compact_count == 0:
            return None, None
        exchanges = tuple(
            SessionExchange(
                interaction_id=str(row.interaction_id),
                user_text=_decrypt_field(self._payload_cipher, row.payload_ciphertext, "text"),
                assistant_text=_decrypt_field(
                    self._payload_cipher, row.response_ciphertext, "content"
                ),
            )
            for row in rows[:compact_count]
        )
        outcome = await self._summarizer.summarize(exchanges)
        if outcome.status != "completed" or not outcome.summary_text:
            logger.warning(
                "Context compaction skipped (session_id=%s, error_class=%s)",
                session_id,
                outcome.error_class,
            )
            return None, None
        return outcome.summary_text, max(1, len(rows) - compact_count)

    async def _persist_response(
        self,
        interaction_id: UUID,
        *,
        content_ciphertext: bytes,
        content_key_version: int,
        content_length: int,
        chunk_count: int,
    ) -> LogicalResponse | None:
        session = await self._session_factory()
        try:
            return await TelegramInteractionsRepository(session).persist_response_ready(
                interaction_id,
                content_ciphertext=content_ciphertext,
                content_key_version=content_key_version,
                content_length=content_length,
                chunk_count=chunk_count,
            )
        finally:
            await session.close()

    async def _persist_command_reply(
        self,
        interaction_id: UUID,
        *,
        agno_session_id: str | None,
        content_ciphertext: bytes,
        content_key_version: int,
        content_length: int,
        chunk_count: int,
        voice_failure_notice: bool = False,
    ) -> LogicalResponse | None:
        session = await self._session_factory()
        try:
            return await TelegramInteractionsRepository(session).claim_command_reply(
                interaction_id,
                agno_session_id=agno_session_id,
                content_ciphertext=content_ciphertext,
                content_key_version=content_key_version,
                content_length=content_length,
                chunk_count=chunk_count,
                **({"voice_failure_notice": True} if voice_failure_notice else {}),
            )
        finally:
            await session.close()

    async def _claim_delivery(self, interaction_id: UUID) -> LogicalResponse | None:
        session = await self._session_factory()
        try:
            return await TelegramInteractionsRepository(session).claim_delivery_start(
                interaction_id
            )
        finally:
            await session.close()

    async def _list_deliveries(
        self,
        logical_response_id: UUID,
    ) -> list[TelegramResponseDelivery]:
        session = await self._session_factory()
        try:
            return await TelegramInteractionsRepository(session).list_response_deliveries(
                logical_response_id
            )
        finally:
            await session.close()

    async def _claim_chunk(
        self,
        logical_response_id: UUID,
        chunk_index: int,
    ) -> TelegramResponseDelivery | None:
        session = await self._session_factory()
        try:
            return await TelegramInteractionsRepository(session).claim_response_chunk(
                logical_response_id, chunk_index
            )
        finally:
            await session.close()

    async def _mark_chunk_delivered(self, delivery_id: UUID, message_id: int) -> None:
        session = await self._session_factory()
        try:
            await TelegramInteractionsRepository(session).mark_response_chunk_delivered(
                delivery_id, message_id
            )
        finally:
            await session.close()

    async def _finalize_delivery(self, interaction_id: UUID, response_id: UUID) -> bool:
        session = await self._session_factory()
        try:
            return await TelegramInteractionsRepository(session).finalize_response_delivery(
                interaction_id, response_id
            )
        finally:
            await session.close()

    async def _fail_delivery(
        self,
        interaction_id: UUID,
        response_id: UUID,
        delivery_id: UUID,
        status: InteractionStatus,
        error_class: str,
    ) -> None:
        session = await self._session_factory()
        try:
            await TelegramInteractionsRepository(session).fail_response_delivery(
                interaction_id,
                response_id,
                delivery_id,
                status=status,
                error_class=error_class,
            )
        finally:
            await session.close()

    async def _mark_terminal(
        self,
        interaction_id: UUID,
        status: InteractionStatus,
        *,
        error_class: str,
        error_detail_code: str,
    ) -> None:
        session = await self._session_factory()
        try:
            await TelegramInteractionsRepository(session).update_status(
                interaction_id,
                status,
                error_class=error_class,
                error_detail_code=error_detail_code,
            )
        finally:
            await session.close()
