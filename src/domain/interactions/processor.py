"""Deterministic processor for accepted interactions and the logical-response outbox."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections import defaultdict
from collections.abc import Awaitable, Callable, Sequence
from typing import Protocol
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.interactions.models import (
    InteractionStatus,
    LogicalResponse,
    TelegramInteraction,
    TelegramResponseDelivery,
)
from src.domain.interactions.outbox import split_telegram_message
from src.domain.interactions.payloads import TelegramPayloadCipher
from src.domain.llm_access.cost_governance import CostGovernanceError
from src.domain.llm_access.models import ExecutionBudgetExceededError
from src.observability import get_telemetry, log_context_scope
from src.repositories.interactions import TelegramInteractionsRepository

logger = logging.getLogger(__name__)


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
    ) -> str: ...


class TelegramResponseSender(Protocol):
    """Outbound Telegram port returning the confirmed Telegram message ID."""

    async def send_text(self, chat_id: int, text: str) -> int: ...

    async def send_typing(self, chat_id: int) -> None: ...


class TelegramSendError(RuntimeError):
    """A Telegram send failure classified by whether no external message was sent."""

    def __init__(self, message: str, *, definitive: bool):
        super().__init__(message)
        self.definitive = definitive


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
        global_concurrency: int = 2,
        batch_size: int = 20,
        typing_refresh_seconds: float = 4.0,
    ):
        self._session_factory = session_factory
        self._payload_cipher = payload_cipher
        self._agent_runner = agent_runner
        self._sender = sender
        self._global_semaphore = asyncio.Semaphore(global_concurrency)
        self._batch_size = batch_size
        self._typing_refresh_seconds = typing_refresh_seconds
        self._chat_locks: dict[int, asyncio.Lock] = {}
        self._user_locks: dict[int, asyncio.Lock] = {}

    async def recover_once(self) -> int:
        """Mark states that may already have side effects as ambiguous after restart."""
        session = await self._session_factory()
        try:
            repository = TelegramInteractionsRepository(session)
            return await repository.mark_inflight_as_ambiguous()
        finally:
            await session.close()

    async def run_once(self) -> int:
        """Recover deterministic work ordered by chat, with bounded parallel chats."""
        session = await self._session_factory()
        try:
            interactions = await TelegramInteractionsRepository(session).list_recoverable_work(
                self._batch_size
            )
        finally:
            await session.close()

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
        return processed

    async def run_forever(self, interval_seconds: float) -> None:
        """Poll recoverable work; errors do not terminate the lifecycle task."""
        while True:
            try:
                await self.run_once()
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

    async def _run_agent(self, interaction: TelegramInteraction) -> bool:
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
            input_text = payload.get("text")
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

        run_id = str(uuid4())
        session_id = f"tg:ancoramind:{interaction.chat_id}"
        claimed = await self._claim_agent(interaction.id, run_id, session_id)
        if claimed is None:
            return False

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
        started = time.perf_counter()
        with (
            log_context_scope(attributes),
            get_telemetry().span("interaction.process", attributes) as span,
        ):
            try:
                content = await self._agent_runner.run(
                    input_text,
                    user_id=str(interaction.telegram_user_id),
                    session_id=session_id,
                    run_id=run_id,
                    correlation_id=interaction.correlation_id,
                    telegram_update_id=interaction.telegram_update_id,
                    telegram_message_id=interaction.telegram_message_id,
                )
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

    async def _refresh_typing(self, chat_id: int) -> None:
        """Keep Telegram's non-content typing indicator alive during an Agent run."""
        while True:
            try:
                await self._sender.send_typing(chat_id)
            except Exception:
                logger.debug("Telegram typing refresh failed", exc_info=True)
            await asyncio.sleep(self._typing_refresh_seconds)

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
                        message_id = await self._sender.send_text(
                            interaction.chat_id,
                            chunks[claimed.chunk_index],
                        )
                        await self._mark_chunk_delivered(claimed.id, message_id)
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

        return await self._finalize_delivery(interaction.id, response.id)

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
