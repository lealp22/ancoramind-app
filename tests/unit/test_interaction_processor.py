"""Unit tests for T5 interaction processor invariants and response chunking."""

from __future__ import annotations

import asyncio
from typing import cast
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from cryptography.fernet import Fernet
from sqlalchemy.ext.asyncio import AsyncSession

import src.domain.interactions.processor as processor_module
from src.domain.context_policy.session_summary import SessionSummaryOutcome
from src.domain.emergency_stop.models import EmergencyStopActiveError
from src.domain.interactions.commands import (
    HELP_REPLY,
    NEW_SESSION_REPLY,
)
from src.domain.interactions.media import ResolvedTelegramMedia
from src.domain.interactions.models import InteractionStatus, TelegramInteraction
from src.domain.interactions.outbox import split_telegram_message
from src.domain.interactions.payloads import TelegramPayloadCipher
from src.domain.interactions.processor import InteractionProcessor, TelegramSendError
from src.domain.interactions.reply import AgentReply
from src.domain.llm_access.cost_governance import CostGovernanceError
from src.domain.llm_access.models import ExecutionBudgetExceededError
from src.repositories.interactions import EncryptedSessionExchange, TelegramInteractionsRepository


def _interaction(status: InteractionStatus = InteractionStatus.ACCEPTED) -> TelegramInteraction:
    return TelegramInteraction.model_validate(
        {
            "id": str(uuid4()),
            "bot_id": 1,
            "telegram_update_id": 2,
            "telegram_message_id": 3,
            "chat_id": 4,
            "telegram_user_id": 5,
            "update_type": "message",
            "status": status,
            "received_at": "2026-09-13T00:00:00Z",
            "accepted_at": "2026-09-13T00:00:00Z",
            "updated_at": "2026-09-13T00:00:00Z",
        }
    )


def test_split_telegram_message_is_deterministic_and_prefers_word_boundary() -> None:
    content = "uno dos tres cuatro"

    assert split_telegram_message(content, limit=10) == ["uno dos", "tres", "cuatro"]
    assert split_telegram_message("abcdefgh", limit=3) == ["abc", "def", "gh"]
    assert split_telegram_message("") == [""]


def test_split_telegram_message_rejects_invalid_limit() -> None:
    with pytest.raises(ValueError, match="positive"):
        split_telegram_message("content", limit=0)


async def test_agent_failure_after_claim_is_marked_ambiguous(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = AsyncMock()
    repo = AsyncMock(spec=TelegramInteractionsRepository)
    interaction = _interaction()
    repo.claim_agent_start_with_run_id.return_value = interaction.model_copy(
        update={"status": InteractionStatus.AGENT_STARTED}
    )
    monkeypatch.setattr(processor_module, "TelegramInteractionsRepository", lambda _: repo)

    cipher = TelegramPayloadCipher(Fernet.generate_key().decode("ascii"), key_version=1)
    encrypted = cipher.encrypt({"text": "hola"})
    accepted = interaction.model_copy(update={"payload_ciphertext": encrypted.ciphertext})
    runner = AsyncMock()
    runner.run.side_effect = RuntimeError("model crashed")
    sender = AsyncMock()
    sender.send_typing.return_value = None

    async def session_factory() -> AsyncSession:
        return cast(AsyncSession, session)

    processor = InteractionProcessor(
        session_factory=session_factory,
        payload_cipher=cipher,
        agent_runner=runner,
        sender=sender,
    )

    assert await processor._run_agent(accepted) is True
    runner.run.assert_awaited_once()
    assert runner.run.await_args.kwargs["telegram_update_id"] == 2
    assert runner.run.await_args.kwargs["telegram_message_id"] == 3
    sender.send_text.assert_not_awaited()
    repo.update_status.assert_awaited_once_with(
        accepted.id,
        InteractionStatus.FAILED_AMBIGUOUS,
        error_class="AgentRunError",
        error_detail_code="agent_run_failed_after_claim",
    )


async def test_budget_exhaustion_after_claim_records_the_budget_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = AsyncMock()
    repo = AsyncMock(spec=TelegramInteractionsRepository)
    interaction = _interaction()
    repo.claim_agent_start_with_run_id.return_value = interaction.model_copy(
        update={"status": InteractionStatus.AGENT_STARTED}
    )
    monkeypatch.setattr(processor_module, "TelegramInteractionsRepository", lambda _: repo)
    cipher = TelegramPayloadCipher(Fernet.generate_key().decode("ascii"), key_version=1)
    accepted = interaction.model_copy(
        update={"payload_ciphertext": cipher.encrypt({"text": "hola"}).ciphertext}
    )
    runner = AsyncMock()
    runner.run.side_effect = ExecutionBudgetExceededError(
        "max_model_calls", "logical model-call ceiling"
    )
    sender = AsyncMock()
    sender.send_typing.return_value = None

    async def session_factory() -> AsyncSession:
        return cast(AsyncSession, session)

    processor = InteractionProcessor(
        session_factory=session_factory,
        payload_cipher=cipher,
        agent_runner=runner,
        sender=sender,
    )

    assert await processor._run_agent(accepted) is True
    repo.update_status.assert_awaited_once_with(
        accepted.id,
        InteractionStatus.FAILED_AMBIGUOUS,
        error_class="ExecutionBudgetExceededError",
        error_detail_code="max_model_calls",
    )


async def test_cost_hard_stop_is_controlled_and_never_replayed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = AsyncMock()
    repo = AsyncMock(spec=TelegramInteractionsRepository)
    interaction = _interaction()
    repo.claim_agent_start_with_run_id.return_value = interaction.model_copy(
        update={"status": InteractionStatus.AGENT_STARTED}
    )
    monkeypatch.setattr(processor_module, "TelegramInteractionsRepository", lambda _: repo)
    cipher = TelegramPayloadCipher(Fernet.generate_key().decode("ascii"), key_version=1)
    accepted = interaction.model_copy(
        update={"payload_ciphertext": cipher.encrypt({"text": "hola"}).ciphertext}
    )
    runner = AsyncMock()
    runner.run.side_effect = CostGovernanceError(
        "daily_budget_exhausted", "today spend exhausted the daily budget"
    )
    sender = AsyncMock()
    sender.send_typing.return_value = None

    async def session_factory() -> AsyncSession:
        return cast(AsyncSession, session)

    processor = InteractionProcessor(
        session_factory=session_factory,
        payload_cipher=cipher,
        agent_runner=runner,
        sender=sender,
    )

    assert await processor._run_agent(accepted) is True
    runner.run.assert_awaited_once()
    sender.send_text.assert_not_awaited()
    repo.update_status.assert_awaited_once_with(
        accepted.id,
        InteractionStatus.FAILED_CONTROLLED,
        error_class="CostGovernanceError",
        error_detail_code="daily_budget_exhausted",
    )


async def test_emergency_stop_is_controlled_and_never_replayed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """BL-44/specs/031: a manual operator stop is deterministic, never replayed."""
    session = AsyncMock()
    repo = AsyncMock(spec=TelegramInteractionsRepository)
    interaction = _interaction()
    repo.claim_agent_start_with_run_id.return_value = interaction.model_copy(
        update={"status": InteractionStatus.AGENT_STARTED}
    )
    monkeypatch.setattr(processor_module, "TelegramInteractionsRepository", lambda _: repo)
    cipher = TelegramPayloadCipher(Fernet.generate_key().decode("ascii"), key_version=1)
    accepted = interaction.model_copy(
        update={"payload_ciphertext": cipher.encrypt({"text": "hola"}).ciphertext}
    )
    runner = AsyncMock()
    runner.run.side_effect = EmergencyStopActiveError("cost spike")
    sender = AsyncMock()
    sender.send_typing.return_value = None

    async def session_factory() -> AsyncSession:
        return cast(AsyncSession, session)

    processor = InteractionProcessor(
        session_factory=session_factory,
        payload_cipher=cipher,
        agent_runner=runner,
        sender=sender,
    )

    assert await processor._run_agent(accepted) is True
    runner.run.assert_awaited_once()
    sender.send_text.assert_not_awaited()
    repo.update_status.assert_awaited_once_with(
        accepted.id,
        InteractionStatus.FAILED_CONTROLLED,
        error_class="EmergencyStopActiveError",
        error_detail_code="emergency_stop_active",
    )


async def test_definitive_telegram_failure_is_not_retried(monkeypatch: pytest.MonkeyPatch) -> None:
    session = AsyncMock()
    repo = AsyncMock(spec=TelegramInteractionsRepository)
    interaction = _interaction(InteractionStatus.RESPONSE_READY)
    response_id = uuid4()
    response = AsyncMock()
    response.id = response_id
    response.content_ciphertext = (
        TelegramPayloadCipher(Fernet.generate_key().decode("ascii"), key_version=1)
        .encrypt({"content": "respuesta"})
        .ciphertext
    )
    response.chunk_count = 1
    delivery = AsyncMock()
    delivery.id = uuid4()
    delivery.chunk_index = 0
    delivery.status = "pending"
    claimed = AsyncMock()
    claimed.id = delivery.id
    claimed.chunk_index = 0

    repo.claim_delivery_start.return_value = response
    repo.list_response_deliveries.return_value = [delivery]
    repo.claim_response_chunk.return_value = claimed
    monkeypatch.setattr(processor_module, "TelegramInteractionsRepository", lambda _: repo)

    cipher = TelegramPayloadCipher(Fernet.generate_key().decode("ascii"), key_version=1)
    response.content_ciphertext = cipher.encrypt({"content": "respuesta"}).ciphertext
    runner = AsyncMock()
    sender = AsyncMock()
    sender.send_typing.return_value = None
    sender.send_text.side_effect = TelegramSendError("bad request", definitive=True)

    async def session_factory() -> AsyncSession:
        return cast(AsyncSession, session)

    processor = InteractionProcessor(
        session_factory=session_factory,
        payload_cipher=cipher,
        agent_runner=runner,
        sender=sender,
    )

    assert await processor._deliver_response(interaction) is True
    sender.send_text.assert_awaited_once_with(4, "respuesta")
    repo.fail_response_delivery.assert_awaited_once_with(
        interaction.id,
        response_id,
        delivery.id,
        status=InteractionStatus.FAILED_DEFINITIVE,
        error_class="TelegramSendError",
    )


async def test_processor_refreshes_typing_while_agent_run_is_pending(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = AsyncMock()
    repo = AsyncMock(spec=TelegramInteractionsRepository)
    interaction = _interaction()
    cipher = TelegramPayloadCipher(Fernet.generate_key().decode("ascii"), key_version=1)
    encrypted = cipher.encrypt({"text": "hola"})
    accepted = interaction.model_copy(update={"payload_ciphertext": encrypted.ciphertext})
    repo.claim_agent_start_with_run_id.return_value = accepted.model_copy(
        update={"status": InteractionStatus.AGENT_STARTED}
    )
    response = AsyncMock()
    response.id = uuid4()
    repo.persist_response_ready.return_value = response
    repo.claim_delivery_start.return_value = None
    monkeypatch.setattr(processor_module, "TelegramInteractionsRepository", lambda _: repo)

    release_runner = asyncio.Event()
    typing_sent = asyncio.Event()

    class SlowRunner:
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
            media=(),
            provenance=None,
            compaction_summary=None,
            reduced_history_runs=None,
        ) -> str:
            assert input_text == "hola"
            assert user_id == "5"
            assert session_id == "tg:ancoramind:4"
            assert run_id
            assert correlation_id == accepted.id
            assert telegram_update_id == 2
            assert telegram_message_id == 3
            assert media == ()
            await release_runner.wait()
            return "respuesta final"

    sender = AsyncMock()

    async def mark_typing(chat_id: int) -> None:
        assert chat_id == 4
        typing_sent.set()

    sender.send_typing.side_effect = mark_typing

    async def session_factory() -> AsyncSession:
        return cast(AsyncSession, session)

    processor = InteractionProcessor(
        session_factory=session_factory,
        payload_cipher=cipher,
        agent_runner=SlowRunner(),
        sender=sender,
        typing_refresh_seconds=0.01,
    )
    task = asyncio.create_task(processor._run_agent(accepted))
    await asyncio.wait_for(typing_sent.wait(), timeout=0.2)
    release_runner.set()
    await task

    assert sender.send_typing.await_count >= 1


async def test_processor_resolves_attachment_after_claim_and_passes_media(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = AsyncMock()
    repo = AsyncMock(spec=TelegramInteractionsRepository)
    interaction = _interaction()
    cipher = TelegramPayloadCipher(Fernet.generate_key().decode("ascii"), key_version=1)
    encrypted = cipher.encrypt(
        {
            "text": None,
            "attachments": [{"kind": "photo", "file_id": "opaque-file-id"}],
        }
    )
    accepted = interaction.model_copy(update={"payload_ciphertext": encrypted.ciphertext})
    repo.claim_agent_start_with_run_id.return_value = accepted.model_copy(
        update={"status": InteractionStatus.AGENT_STARTED}
    )
    response = AsyncMock()
    response.id = uuid4()
    repo.persist_response_ready.return_value = response
    repo.claim_delivery_start.return_value = None
    monkeypatch.setattr(processor_module, "TelegramInteractionsRepository", lambda _: repo)

    resolver = AsyncMock()
    resolved = ResolvedTelegramMedia(
        content=b"\xff\xd8\xffJPEG",
        filename="telegram-document.jpg",
        mime_type="image/jpeg",
        is_image=True,
    )
    resolver.resolve.return_value = resolved
    runner = AsyncMock()
    runner.run.return_value = "📄 archivado"
    sender = AsyncMock()

    async def session_factory() -> AsyncSession:
        return cast(AsyncSession, session)

    processor = InteractionProcessor(
        session_factory=session_factory,
        payload_cipher=cipher,
        agent_runner=runner,
        sender=sender,
        media_resolver=resolver,
    )

    assert await processor._run_agent(accepted) is False
    repo.claim_agent_start_with_run_id.assert_awaited_once()
    resolver.resolve.assert_awaited_once()
    assert runner.run.await_args.kwargs["media"] == (resolved,)
    assert "analyze_document" in runner.run.await_args.args[0]


def _attachment_bearing_interaction(
    cipher: TelegramPayloadCipher,
) -> TelegramInteraction:
    interaction = _interaction()
    encrypted = cipher.encrypt(
        {"text": None, "attachments": [{"kind": "photo", "file_id": "opaque-file-id"}]}
    )
    return interaction.model_copy(update={"payload_ciphertext": encrypted.ciphertext})


def _fast_ack_processor(
    *,
    repo: AsyncMock,
    session: AsyncMock,
    fast_ack_enabled: bool,
    cipher: TelegramPayloadCipher,
) -> InteractionProcessor:
    resolver = AsyncMock()
    resolver.resolve.return_value = ResolvedTelegramMedia(
        content=b"\xff\xd8\xffJPEG",
        filename="telegram-document.jpg",
        mime_type="image/jpeg",
        is_image=True,
    )
    runner = AsyncMock()
    runner.run.return_value = "📄 archivado"
    sender = AsyncMock()
    sender.send_text.return_value = 999

    async def session_factory() -> AsyncSession:
        return cast(AsyncSession, session)

    return InteractionProcessor(
        session_factory=session_factory,
        payload_cipher=cipher,
        agent_runner=runner,
        sender=sender,
        media_resolver=resolver,
        fast_ack_enabled=fast_ack_enabled,
    )


async def test_fast_ack_sent_once_for_attachment_bearing_interaction_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """BL-32: an attachment-bearing interaction gets an early ack before the Agent run."""
    session = AsyncMock()
    repo = AsyncMock(spec=TelegramInteractionsRepository)
    cipher = TelegramPayloadCipher(Fernet.generate_key().decode("ascii"), key_version=1)
    accepted = _attachment_bearing_interaction(cipher)
    repo.claim_agent_start_with_run_id.return_value = accepted.model_copy(
        update={"status": InteractionStatus.AGENT_STARTED}
    )
    ack_delivery_id = uuid4()
    repo.create_ack_response.return_value = ack_delivery_id
    response = AsyncMock()
    response.id = uuid4()
    repo.persist_response_ready.return_value = response
    repo.claim_delivery_start.return_value = None
    monkeypatch.setattr(processor_module, "TelegramInteractionsRepository", lambda _: repo)

    processor = _fast_ack_processor(
        repo=repo, session=session, fast_ack_enabled=True, cipher=cipher
    )

    await processor._run_agent(accepted)

    repo.create_ack_response.assert_awaited_once()
    assert repo.create_ack_response.await_args.args[0] == accepted.id
    processor._sender.send_text.assert_any_await(  # type: ignore[attr-defined]
        accepted.chat_id, "📄 Documento recibido, analizando…"
    )
    repo.mark_ack_delivery_outcome.assert_awaited_once_with(
        ack_delivery_id, status="delivered", telegram_message_id=999, error_class=None
    )


async def test_fast_ack_not_sent_for_text_only_interaction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = AsyncMock()
    repo = AsyncMock(spec=TelegramInteractionsRepository)
    cipher = TelegramPayloadCipher(Fernet.generate_key().decode("ascii"), key_version=1)
    interaction = _interaction()
    accepted = interaction.model_copy(
        update={"payload_ciphertext": cipher.encrypt({"text": "hola"}).ciphertext}
    )
    repo.claim_agent_start_with_run_id.return_value = accepted.model_copy(
        update={"status": InteractionStatus.AGENT_STARTED}
    )
    response = AsyncMock()
    response.id = uuid4()
    repo.persist_response_ready.return_value = response
    repo.claim_delivery_start.return_value = None
    monkeypatch.setattr(processor_module, "TelegramInteractionsRepository", lambda _: repo)

    processor = _fast_ack_processor(
        repo=repo, session=session, fast_ack_enabled=True, cipher=cipher
    )

    await processor._run_agent(accepted)

    repo.create_ack_response.assert_not_awaited()


async def test_fast_ack_not_sent_when_flag_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    session = AsyncMock()
    repo = AsyncMock(spec=TelegramInteractionsRepository)
    cipher = TelegramPayloadCipher(Fernet.generate_key().decode("ascii"), key_version=1)
    accepted = _attachment_bearing_interaction(cipher)
    repo.claim_agent_start_with_run_id.return_value = accepted.model_copy(
        update={"status": InteractionStatus.AGENT_STARTED}
    )
    response = AsyncMock()
    response.id = uuid4()
    repo.persist_response_ready.return_value = response
    repo.claim_delivery_start.return_value = None
    monkeypatch.setattr(processor_module, "TelegramInteractionsRepository", lambda _: repo)

    processor = _fast_ack_processor(
        repo=repo, session=session, fast_ack_enabled=False, cipher=cipher
    )

    await processor._run_agent(accepted)

    repo.create_ack_response.assert_not_awaited()


async def test_fast_ack_skipped_without_resending_when_already_created(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A reprocessed update must never duplicate the ack (idempotent insert)."""
    session = AsyncMock()
    repo = AsyncMock(spec=TelegramInteractionsRepository)
    cipher = TelegramPayloadCipher(Fernet.generate_key().decode("ascii"), key_version=1)
    accepted = _attachment_bearing_interaction(cipher)
    repo.claim_agent_start_with_run_id.return_value = accepted.model_copy(
        update={"status": InteractionStatus.AGENT_STARTED}
    )
    repo.create_ack_response.return_value = None  # already exists
    response = AsyncMock()
    response.id = uuid4()
    repo.persist_response_ready.return_value = response
    repo.claim_delivery_start.return_value = None
    monkeypatch.setattr(processor_module, "TelegramInteractionsRepository", lambda _: repo)

    processor = _fast_ack_processor(
        repo=repo, session=session, fast_ack_enabled=True, cipher=cipher
    )

    await processor._run_agent(accepted)

    repo.create_ack_response.assert_awaited_once()
    processor._sender.send_text.assert_not_awaited()  # type: ignore[attr-defined]
    repo.mark_ack_delivery_outcome.assert_not_awaited()


async def test_fast_ack_send_failure_does_not_block_the_main_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A fast-ack send failure is recorded and swallowed — the main run still completes."""
    session = AsyncMock()
    repo = AsyncMock(spec=TelegramInteractionsRepository)
    cipher = TelegramPayloadCipher(Fernet.generate_key().decode("ascii"), key_version=1)
    accepted = _attachment_bearing_interaction(cipher)
    repo.claim_agent_start_with_run_id.return_value = accepted.model_copy(
        update={"status": InteractionStatus.AGENT_STARTED}
    )
    ack_delivery_id = uuid4()
    repo.create_ack_response.return_value = ack_delivery_id
    response = AsyncMock()
    response.id = uuid4()
    repo.persist_response_ready.return_value = response
    repo.claim_delivery_start.return_value = None
    monkeypatch.setattr(processor_module, "TelegramInteractionsRepository", lambda _: repo)

    processor = _fast_ack_processor(
        repo=repo, session=session, fast_ack_enabled=True, cipher=cipher
    )
    processor._sender.send_text.side_effect = [  # type: ignore[attr-defined]
        TelegramSendError("boom", definitive=False),
        999,
    ]

    result = await processor._run_agent(accepted)

    repo.mark_ack_delivery_outcome.assert_awaited_once_with(
        ack_delivery_id, status="failed", telegram_message_id=None, error_class="TelegramSendError"
    )
    # The main run proceeds and still reaches its own completion path.
    assert isinstance(result, bool)
    processor._agent_runner.run.assert_awaited_once()  # type: ignore[attr-defined]


async def test_fast_ack_persistence_failure_does_not_block_the_main_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = AsyncMock()
    repo = AsyncMock(spec=TelegramInteractionsRepository)
    cipher = TelegramPayloadCipher(Fernet.generate_key().decode("ascii"), key_version=1)
    accepted = _attachment_bearing_interaction(cipher)
    repo.claim_agent_start_with_run_id.return_value = accepted.model_copy(
        update={"status": InteractionStatus.AGENT_STARTED}
    )
    repo.create_ack_response.side_effect = RuntimeError("database down")
    response = AsyncMock()
    response.id = uuid4()
    repo.persist_response_ready.return_value = response
    repo.claim_delivery_start.return_value = None
    monkeypatch.setattr(processor_module, "TelegramInteractionsRepository", lambda _: repo)

    processor = _fast_ack_processor(
        repo=repo, session=session, fast_ack_enabled=True, cipher=cipher
    )

    await processor._run_agent(accepted)

    processor._agent_runner.run.assert_awaited_once()  # type: ignore[attr-defined]


async def test_command_is_answered_deterministically_without_an_agent_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = AsyncMock()
    repo = AsyncMock(spec=TelegramInteractionsRepository)
    interaction = _interaction()
    cipher = TelegramPayloadCipher(Fernet.generate_key().decode("ascii"), key_version=1)
    accepted = interaction.model_copy(
        update={"payload_ciphertext": cipher.encrypt({"text": "/help"}).ciphertext}
    )
    response = AsyncMock()
    response.id = uuid4()
    repo.claim_command_reply.return_value = response
    repo.claim_delivery_start.return_value = None
    monkeypatch.setattr(processor_module, "TelegramInteractionsRepository", lambda _: repo)

    runner = AsyncMock()
    sender = AsyncMock()

    async def session_factory() -> AsyncSession:
        return cast(AsyncSession, session)

    processor = InteractionProcessor(
        session_factory=session_factory,
        payload_cipher=cipher,
        agent_runner=runner,
        sender=sender,
    )

    assert await processor._run_agent(accepted) is False

    runner.run.assert_not_awaited()
    sender.send_typing.assert_not_awaited()
    kwargs = repo.claim_command_reply.await_args.kwargs
    assert kwargs["agno_session_id"] is None
    assert kwargs["content_length"] == len(HELP_REPLY)
    assert kwargs["chunk_count"] == 1
    assert cipher.decrypt(kwargs["content_ciphertext"]) == {"content": HELP_REPLY}


async def test_new_command_opens_the_next_conversation_generation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = AsyncMock()
    repo = AsyncMock(spec=TelegramInteractionsRepository)
    interaction = _interaction()
    cipher = TelegramPayloadCipher(Fernet.generate_key().decode("ascii"), key_version=1)
    accepted = interaction.model_copy(
        update={"payload_ciphertext": cipher.encrypt({"text": "/new"}).ciphertext}
    )
    response = AsyncMock()
    response.id = uuid4()
    repo.current_session_id.return_value = "tg:ancoramind:4"
    repo.claim_command_reply.return_value = response
    repo.claim_delivery_start.return_value = None
    monkeypatch.setattr(processor_module, "TelegramInteractionsRepository", lambda _: repo)

    async def session_factory() -> AsyncSession:
        return cast(AsyncSession, session)

    processor = InteractionProcessor(
        session_factory=session_factory,
        payload_cipher=cipher,
        agent_runner=AsyncMock(),
        sender=AsyncMock(),
    )

    assert await processor._run_agent(accepted) is False

    kwargs = repo.claim_command_reply.await_args.kwargs
    assert kwargs["agno_session_id"] == "tg:ancoramind:4:1"
    assert cipher.decrypt(kwargs["content_ciphertext"]) == {"content": NEW_SESSION_REPLY}


async def test_a_replayed_command_never_answers_twice(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = AsyncMock()
    repo = AsyncMock(spec=TelegramInteractionsRepository)
    interaction = _interaction()
    cipher = TelegramPayloadCipher(Fernet.generate_key().decode("ascii"), key_version=1)
    accepted = interaction.model_copy(
        update={"payload_ciphertext": cipher.encrypt({"text": "/new"}).ciphertext}
    )
    repo.claim_command_reply.return_value = None
    monkeypatch.setattr(processor_module, "TelegramInteractionsRepository", lambda _: repo)

    sender = AsyncMock()

    async def session_factory() -> AsyncSession:
        return cast(AsyncSession, session)

    processor = InteractionProcessor(
        session_factory=session_factory,
        payload_cipher=cipher,
        agent_runner=AsyncMock(),
        sender=sender,
    )

    assert await processor._run_agent(accepted) is False

    repo.claim_delivery_start.assert_not_awaited()
    sender.send_text.assert_not_awaited()


async def test_leading_slash_text_that_is_not_a_command_reaches_the_agent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = AsyncMock()
    repo = AsyncMock(spec=TelegramInteractionsRepository)
    interaction = _interaction()
    cipher = TelegramPayloadCipher(Fernet.generate_key().decode("ascii"), key_version=1)
    accepted = interaction.model_copy(
        update={"payload_ciphertext": cipher.encrypt({"text": "/home/user/notas.txt"}).ciphertext}
    )
    repo.claim_agent_start_with_run_id.return_value = accepted.model_copy(
        update={"status": InteractionStatus.AGENT_STARTED}
    )
    response = AsyncMock()
    response.id = uuid4()
    repo.persist_response_ready.return_value = response
    repo.claim_delivery_start.return_value = None
    monkeypatch.setattr(processor_module, "TelegramInteractionsRepository", lambda _: repo)

    runner = AsyncMock()
    runner.run.return_value = "ok"

    async def session_factory() -> AsyncSession:
        return cast(AsyncSession, session)

    processor = InteractionProcessor(
        session_factory=session_factory,
        payload_cipher=cipher,
        agent_runner=runner,
        sender=AsyncMock(),
    )

    assert await processor._run_agent(accepted) is False

    runner.run.assert_awaited_once()
    assert runner.run.await_args.args[0] == "/home/user/notas.txt"
    repo.claim_command_reply.assert_not_awaited()


async def test_agent_run_reuses_the_stored_conversation_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = AsyncMock()
    repo = AsyncMock(spec=TelegramInteractionsRepository)
    interaction = _interaction()
    cipher = TelegramPayloadCipher(Fernet.generate_key().decode("ascii"), key_version=1)
    accepted = interaction.model_copy(
        update={"payload_ciphertext": cipher.encrypt({"text": "hola"}).ciphertext}
    )
    repo.current_session_id.return_value = "tg:ancoramind:4:3"
    repo.claim_agent_start_with_run_id.return_value = accepted.model_copy(
        update={"status": InteractionStatus.AGENT_STARTED}
    )
    response = AsyncMock()
    response.id = uuid4()
    repo.persist_response_ready.return_value = response
    repo.claim_delivery_start.return_value = None
    monkeypatch.setattr(processor_module, "TelegramInteractionsRepository", lambda _: repo)

    runner = AsyncMock()
    runner.run.return_value = "ok"

    async def session_factory() -> AsyncSession:
        return cast(AsyncSession, session)

    processor = InteractionProcessor(
        session_factory=session_factory,
        payload_cipher=cipher,
        agent_runner=runner,
        sender=AsyncMock(),
    )

    assert await processor._run_agent(accepted) is False

    assert runner.run.await_args.kwargs["session_id"] == "tg:ancoramind:4:3"
    assert repo.claim_agent_start_with_run_id.await_args.args[2] == "tg:ancoramind:4:3"


async def test_same_chat_is_processed_in_order(monkeypatch: pytest.MonkeyPatch) -> None:
    session = AsyncMock()
    repo = AsyncMock(spec=TelegramInteractionsRepository)
    first = _interaction()
    second = first.model_copy(update={"id": uuid4(), "telegram_update_id": 3})
    calls: list[UUID] = []

    async def fake_run_agent(interaction: TelegramInteraction) -> bool:
        calls.append(interaction.id)
        return True

    monkeypatch.setattr(processor_module, "TelegramInteractionsRepository", lambda _: repo)

    async def session_factory() -> AsyncSession:
        return cast(AsyncSession, session)

    processor = InteractionProcessor(
        session_factory=session_factory,
        payload_cipher=TelegramPayloadCipher(Fernet.generate_key().decode("ascii"), key_version=1),
        agent_runner=AsyncMock(),
        sender=AsyncMock(),
    )
    monkeypatch.setattr(processor, "_run_agent", fake_run_agent)

    assert await processor._process_chat_queue([first, second]) == 2
    assert calls == [first.id, second.id]


def _consent_processor(
    monkeypatch: pytest.MonkeyPatch, actions_repo: AsyncMock
) -> InteractionProcessor:
    session = AsyncMock()

    async def session_factory() -> AsyncSession:
        return cast(AsyncSession, session)

    monkeypatch.setattr(processor_module, "ActionProposalsRepository", lambda _: actions_repo)
    executor = AsyncMock()

    async def execute(proposal, *, user_id):
        assert user_id == "5"
        return f"✅ Confirmado y ejecutado ({proposal.id})."

    executor.execute.side_effect = execute
    monkeypatch.setattr(processor_module, "ProposalExecutor", lambda *args, **kwargs: executor)
    return InteractionProcessor(
        session_factory=session_factory,
        payload_cipher=TelegramPayloadCipher(Fernet.generate_key().decode("ascii"), key_version=1),
        agent_runner=AsyncMock(),
        sender=AsyncMock(),
        governed_consent=True,
    )


@pytest.mark.parametrize("answer", ["", "Estas son tus tareas: Comprar café completada."])
async def test_proposal_composition_replaces_only_proposal_narration(monkeypatch, answer) -> None:
    actions = AsyncMock()
    proposal_id = uuid4()
    actions.list_created_in_interaction.return_value = [
        {
            "id": proposal_id,
            "tool_name": "create_todo_item",
            "payload": {
                "title": "Renovar seguro",
                "priority": "high",
                "due_date": "2026-10-20T00:00:00",
            },
        },
    ]
    processor = _consent_processor(monkeypatch, actions)
    reply = AgentReply(answer=answer, proposal_text="Renovar seguro, alta. ¿Confirmas?")
    interaction = _interaction()
    content = await processor._append_proposal_blocks(interaction, reply)
    assert content.count("Renovar seguro") == 1
    assert content.count("Pulsa ✅ Sí") == 1
    assert "¿Confirmas?" not in content
    assert "Prioridad: alta" in content
    assert "20 de octubre de 2026" in content
    assert content.startswith(answer) if answer else content.startswith("📋")
    assert reply.proposal_text == "Renovar seguro, alta. ¿Confirmas?"
    actions.list_created_in_interaction.assert_awaited_once_with(interaction.id, user_id="5")


async def test_multiple_proposals_keep_one_block_and_button_pair_per_id(monkeypatch) -> None:
    actions = AsyncMock()
    ids = [uuid4(), uuid4()]
    actions.list_created_in_interaction.return_value = [
        {"id": pid, "tool_name": "create_todo_list", "payload": {"name": name}}
        for pid, name in zip(ids, ["Trabajo", "Personal"], strict=True)
    ]
    processor = _consent_processor(monkeypatch, actions)
    content = await processor._append_proposal_blocks(
        _interaction(),
        AgentReply(answer="Consulta independiente.", proposal_text="¿Confirmas ambas?"),
    )
    assert content.startswith("Consulta independiente.")
    assert content.count("📋 **Propuesta**") == 2
    assert content.count("Pulsa ✅ Sí") == 2
    assert "ambas" not in content
    buttons = await processor._pending_proposal_buttons(_interaction())
    assert [pair[0].callback_data for pair in buttons] == [f"c:{pid}" for pid in ids]
    assert [pair[1].callback_data for pair in buttons] == [f"d:{pid}" for pid in ids]


@pytest.mark.parametrize("governed", [False, True])
async def test_no_stored_proposal_never_replaces_an_answer_or_creates_controls(
    monkeypatch, governed
) -> None:
    actions = AsyncMock()
    actions.list_created_in_interaction.return_value = []
    processor = _consent_processor(monkeypatch, actions)
    processor._governed_consent = governed
    reply = AgentReply(
        answer="No encontré la lista.", proposal_text="No se creó ninguna propuesta."
    )
    assert await processor._append_proposal_blocks(_interaction(), reply) == reply.answer
    if not governed:
        actions.list_created_in_interaction.assert_not_awaited()


@pytest.mark.parametrize("governed", [False, True])
async def test_unbacked_proposal_narration_is_never_delivered(monkeypatch, governed) -> None:
    actions = AsyncMock()
    actions.list_created_in_interaction.return_value = []
    processor = _consent_processor(monkeypatch, actions)
    processor._governed_consent = governed
    content = await processor._append_proposal_blocks(
        _interaction(),
        AgentReply(answer="", proposal_text="He creado una propuesta para Casa. Confirma."),
    )
    assert content == "No se ha presentado ninguna propuesta para confirmar."
    assert "He creado" not in content
    assert await processor._pending_proposal_buttons(_interaction()) == ()


async def test_plain_text_adapter_cannot_guess_proposal_partition(monkeypatch) -> None:
    actions = AsyncMock()
    actions.list_created_in_interaction.return_value = [
        {"id": uuid4(), "tool_name": "create_todo_list", "payload": {"name": "Compras"}}
    ]
    processor = _consent_processor(monkeypatch, actions)
    with pytest.raises(ValueError, match="partitioned Agent reply"):
        await processor._append_proposal_blocks(_interaction(), "READ answer and proposal summary")


@pytest.mark.parametrize(
    "reply,created,expected",
    [
        (AgentReply(answer="", proposal_text="Propuesta creada."), True, "Nombre: Compras"),
        (AgentReply(answer="✅ Añadido y auditado.", proposal_text=""), False, "✅ Añadido"),
        ("", False, None),
        (
            AgentReply(answer="Se borrarán 3 tareas.", proposal_text="¿Confirmas?"),
            True,
            "Se borrarán 3 tareas.",
        ),
    ],
)
async def test_partition_flows_through_encrypted_outbox_without_false_empty_reply(
    monkeypatch, reply, created, expected
) -> None:
    from src.repositories.actions import ActionProposalsRepository

    session = AsyncMock(spec=AsyncSession)
    ledger = AsyncMock(spec=TelegramInteractionsRepository)
    actions = AsyncMock(spec=ActionProposalsRepository)
    actions.list_created_in_interaction.return_value = (
        [{"id": uuid4(), "tool_name": "create_todo_list", "payload": {"name": "Compras"}}]
        if created
        else []
    )
    cipher = TelegramPayloadCipher(Fernet.generate_key().decode("ascii"), key_version=1)
    accepted = _interaction().model_copy(
        update={
            "payload_ciphertext": cipher.encrypt({"text": "Petición sintética"}).ciphertext,
        }
    )
    ledger.claim_agent_start_with_run_id.return_value = accepted.model_copy(
        update={"status": InteractionStatus.AGENT_STARTED}
    )
    ledger.persist_response_ready.return_value = AsyncMock(id=uuid4())
    ledger.claim_delivery_start.return_value = None
    monkeypatch.setattr(processor_module, "TelegramInteractionsRepository", lambda _: ledger)
    monkeypatch.setattr(processor_module, "ActionProposalsRepository", lambda _: actions)
    runner = AsyncMock()
    runner.run.return_value = reply

    async def sessions():
        return session

    processor = InteractionProcessor(
        session_factory=sessions,
        payload_cipher=cipher,
        agent_runner=runner,
        sender=AsyncMock(),
        governed_consent=True,
    )
    await processor._run_agent(accepted)
    runner.run.assert_awaited_once()
    actions.claim_confirmation.assert_not_awaited()
    actions.mark_presented.assert_not_awaited()  # no verified Telegram delivery
    if expected is None:
        ledger.persist_response_ready.assert_not_awaited()
        assert ledger.update_status.await_args.kwargs["error_class"] == "EmptyAgentResponse"
    else:
        stored = ledger.persist_response_ready.await_args.kwargs
        content = cipher.decrypt(stored["content_ciphertext"])["content"]
        assert expected in content
        assert "¿Confirmas?" not in content
        assert content.count("📋 **Propuesta**") == int(created)


class TestConsentInput:
    """specs/023 T4.3: resolving Sí/No before the Agent, with mocked repositories."""

    async def test_non_consent_text_falls_through(self, monkeypatch: pytest.MonkeyPatch) -> None:
        processor = _consent_processor(monkeypatch, AsyncMock())
        assert await processor._handle_consent_input(_interaction(), "hola, qué tal") is None

    async def test_bare_si_with_no_pending_proposals(self, monkeypatch: pytest.MonkeyPatch) -> None:
        actions = AsyncMock()
        actions.list_confirmable.return_value = []
        processor = _consent_processor(monkeypatch, actions)

        reply = await processor._handle_consent_input(_interaction(), "Sí")

        assert reply == "No tienes ninguna propuesta pendiente de confirmar."
        actions.claim_confirmation.assert_not_awaited()

    async def test_bare_si_with_several_pending_asks_to_pick(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        a, b = uuid4(), uuid4()
        actions = AsyncMock()
        actions.list_confirmable.return_value = [a, b]
        processor = _consent_processor(monkeypatch, actions)

        reply = await processor._handle_consent_input(_interaction(), "Sí")

        assert str(a) in reply and str(b) in reply
        actions.claim_confirmation.assert_not_awaited()

    async def test_bare_si_with_exactly_one_pending_claims_it(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from src.domain.actions.models import ClaimedProposal, ConsentClaimResult

        proposal_id = uuid4()
        actions = AsyncMock()
        actions.list_confirmable.return_value = [proposal_id]
        actions.claim_confirmation.return_value = ConsentClaimResult(
            claimed=ClaimedProposal(
                id=proposal_id,
                tool_name="create_reminder",
                payload={},
                source_document_id=None,
                confirming_interaction_id=uuid4(),
            )
        )
        processor = _consent_processor(monkeypatch, actions)

        reply = await processor._handle_consent_input(_interaction(), "Sí")

        assert str(proposal_id) in reply
        actions.claim_confirmation.assert_awaited_once()

    async def test_si_with_uuid_claims_that_proposal(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from src.domain.actions.models import ClaimedProposal, ConsentClaimResult

        proposal_id = uuid4()
        actions = AsyncMock()
        actions.claim_confirmation.return_value = ConsentClaimResult(
            claimed=ClaimedProposal(
                id=proposal_id,
                tool_name="create_reminder",
                payload={},
                source_document_id=None,
                confirming_interaction_id=uuid4(),
            )
        )
        processor = _consent_processor(monkeypatch, actions)

        reply = await processor._handle_consent_input(_interaction(), f"Sí {proposal_id}")

        assert str(proposal_id) in reply
        actions.list_confirmable.assert_not_awaited()

    async def test_rejection_reasons_produce_distinct_fixed_replies(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from src.domain.actions.models import ConsentClaimResult, ConsentRejection

        proposal_id = uuid4()
        cases = (
            (ConsentRejection.NOT_FOUND, "no encontré"),
            (ConsentRejection.EXPIRED, "caducó"),
            (ConsentRejection.INTERACTION_ALREADY_USED, "ya has confirmado"),
            (ConsentRejection.NOT_PENDING, "ya no está pendiente"),
        )
        for rejection, expected_snippet in cases:
            actions = AsyncMock()
            actions.claim_confirmation.return_value = ConsentClaimResult(rejection=rejection)
            processor = _consent_processor(monkeypatch, actions)
            reply = await processor._handle_consent_input(_interaction(), f"Sí {proposal_id}")
            assert expected_snippet in reply.lower()

    async def test_confirm_button_claims_without_touching_discard(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from src.domain.actions.models import ClaimedProposal, ConsentClaimResult

        proposal_id = uuid4()
        actions = AsyncMock()
        actions.claim_confirmation.return_value = ConsentClaimResult(
            claimed=ClaimedProposal(
                id=proposal_id,
                tool_name="create_reminder",
                payload={},
                source_document_id=None,
                confirming_interaction_id=uuid4(),
            )
        )
        processor = _consent_processor(monkeypatch, actions)

        reply = await processor._handle_consent_input(_interaction(), f"c:{proposal_id}")

        assert str(proposal_id) in reply
        actions.discard_proposal.assert_not_awaited()

    async def test_discard_button_discards_without_claiming(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        actions = AsyncMock()
        actions.discard_proposal.return_value = True
        processor = _consent_processor(monkeypatch, actions)

        reply = await processor._handle_consent_input(_interaction(), f"d:{uuid4()}")

        assert reply == "❌ Propuesta descartada."
        actions.claim_confirmation.assert_not_awaited()

    async def test_discard_button_on_already_resolved_proposal(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        actions = AsyncMock()
        actions.discard_proposal.return_value = False
        processor = _consent_processor(monkeypatch, actions)

        reply = await processor._handle_consent_input(_interaction(), f"d:{uuid4()}")

        assert reply == "Esa propuesta ya no está pendiente."

    async def test_malformed_callback_like_text_is_not_consent(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        actions = AsyncMock()
        processor = _consent_processor(monkeypatch, actions)

        for raw in ("c:not-a-uuid", "x:" + str(uuid4()), "c:" + str(uuid4()) + " extra"):
            assert await processor._handle_consent_input(_interaction(), raw) is None
        actions.claim_confirmation.assert_not_awaited()
        actions.discard_proposal.assert_not_awaited()


def _compaction_interaction(cipher: TelegramPayloadCipher) -> TelegramInteraction:
    interaction = _interaction()
    encrypted = cipher.encrypt({"text": "hola"})
    return interaction.model_copy(update={"payload_ciphertext": encrypted.ciphertext})


def _compaction_processor(
    *,
    session: AsyncMock,
    cipher: TelegramPayloadCipher,
    summarizer: AsyncMock | None,
    context_compaction_enabled: bool,
) -> InteractionProcessor:
    runner = AsyncMock()
    runner.run.return_value = "respuesta"
    sender = AsyncMock()

    async def session_factory() -> AsyncSession:
        return cast(AsyncSession, session)

    return InteractionProcessor(
        session_factory=session_factory,
        payload_cipher=cipher,
        agent_runner=runner,
        sender=sender,
        summarizer=summarizer,
        context_compaction_enabled=context_compaction_enabled,
        context_compaction_token_threshold=1_000,
        context_compaction_ratio=0.4,
    )


async def test_compaction_disabled_never_queries_usage_or_exchanges(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = AsyncMock()
    repo = AsyncMock(spec=TelegramInteractionsRepository)
    usage_repo = AsyncMock()
    cipher = TelegramPayloadCipher(Fernet.generate_key().decode("ascii"), key_version=1)
    accepted = _compaction_interaction(cipher)
    repo.claim_agent_start_with_run_id.return_value = accepted.model_copy(
        update={"status": InteractionStatus.AGENT_STARTED}
    )
    response = AsyncMock()
    response.id = uuid4()
    repo.persist_response_ready.return_value = response
    repo.claim_delivery_start.return_value = None
    monkeypatch.setattr(processor_module, "TelegramInteractionsRepository", lambda _: repo)
    monkeypatch.setattr(processor_module, "LlmUsageRepository", lambda _: usage_repo)
    processor = _compaction_processor(
        session=session, cipher=cipher, summarizer=AsyncMock(), context_compaction_enabled=False
    )

    await processor._run_agent(accepted)

    usage_repo.sum_session_tokens.assert_not_awaited()
    repo.list_session_exchanges.assert_not_awaited()
    assert processor._agent_runner.run.await_args.kwargs["compaction_summary"] is None  # type: ignore[attr-defined]
    assert processor._agent_runner.run.await_args.kwargs["reduced_history_runs"] is None  # type: ignore[attr-defined]


async def test_compaction_enabled_but_under_threshold_skips_the_expensive_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = AsyncMock()
    repo = AsyncMock(spec=TelegramInteractionsRepository)
    usage_repo = AsyncMock()
    usage_repo.sum_session_tokens.return_value = 10
    cipher = TelegramPayloadCipher(Fernet.generate_key().decode("ascii"), key_version=1)
    accepted = _compaction_interaction(cipher)
    repo.claim_agent_start_with_run_id.return_value = accepted.model_copy(
        update={"status": InteractionStatus.AGENT_STARTED}
    )
    response = AsyncMock()
    response.id = uuid4()
    repo.persist_response_ready.return_value = response
    repo.claim_delivery_start.return_value = None
    monkeypatch.setattr(processor_module, "TelegramInteractionsRepository", lambda _: repo)
    monkeypatch.setattr(processor_module, "LlmUsageRepository", lambda _: usage_repo)
    processor = _compaction_processor(
        session=session, cipher=cipher, summarizer=AsyncMock(), context_compaction_enabled=True
    )

    await processor._run_agent(accepted)

    usage_repo.sum_session_tokens.assert_awaited_once()
    repo.list_session_exchanges.assert_not_awaited()
    assert processor._agent_runner.run.await_args.kwargs["compaction_summary"] is None  # type: ignore[attr-defined]


async def test_compaction_over_threshold_summarizes_the_oldest_slice(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = AsyncMock()
    repo = AsyncMock(spec=TelegramInteractionsRepository)
    usage_repo = AsyncMock()
    usage_repo.sum_session_tokens.return_value = 5_000
    cipher = TelegramPayloadCipher(Fernet.generate_key().decode("ascii"), key_version=1)
    accepted = _compaction_interaction(cipher)
    repo.claim_agent_start_with_run_id.return_value = accepted.model_copy(
        update={"status": InteractionStatus.AGENT_STARTED}
    )
    response = AsyncMock()
    response.id = uuid4()
    repo.persist_response_ready.return_value = response
    repo.claim_delivery_start.return_value = None
    old_payload = cipher.encrypt({"text": "mensaje antiguo"}).ciphertext
    old_response = cipher.encrypt({"content": "respuesta antigua"}).ciphertext
    repo.list_session_exchanges.return_value = [
        EncryptedSessionExchange(
            interaction_id=uuid4(), payload_ciphertext=old_payload, response_ciphertext=old_response
        )
        for _ in range(5)
    ]
    monkeypatch.setattr(processor_module, "TelegramInteractionsRepository", lambda _: repo)
    monkeypatch.setattr(processor_module, "LlmUsageRepository", lambda _: usage_repo)
    summarizer = AsyncMock()
    summarizer.summarize.return_value = SessionSummaryOutcome(
        summary_text="Resumen de lo antiguo.", status="completed"
    )
    processor = _compaction_processor(
        session=session, cipher=cipher, summarizer=summarizer, context_compaction_enabled=True
    )

    await processor._run_agent(accepted)

    summarizer.summarize.assert_awaited_once()
    [exchanges] = summarizer.summarize.await_args.args
    assert len(exchanges) == 2  # oldest_fraction_count(5, 0.4) == 2
    assert exchanges[0].user_text == "mensaje antiguo"
    assert exchanges[0].assistant_text == "respuesta antigua"
    kwargs = processor._agent_runner.run.await_args.kwargs  # type: ignore[attr-defined]
    assert kwargs["compaction_summary"] == "Resumen de lo antiguo."
    assert kwargs["reduced_history_runs"] == 3


async def test_compaction_failure_does_not_block_the_main_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = AsyncMock()
    repo = AsyncMock(spec=TelegramInteractionsRepository)
    usage_repo = AsyncMock()
    usage_repo.sum_session_tokens.return_value = 5_000
    cipher = TelegramPayloadCipher(Fernet.generate_key().decode("ascii"), key_version=1)
    accepted = _compaction_interaction(cipher)
    repo.claim_agent_start_with_run_id.return_value = accepted.model_copy(
        update={"status": InteractionStatus.AGENT_STARTED}
    )
    response = AsyncMock()
    response.id = uuid4()
    repo.persist_response_ready.return_value = response
    repo.claim_delivery_start.return_value = None
    old_payload = cipher.encrypt({"text": "mensaje antiguo"}).ciphertext
    repo.list_session_exchanges.return_value = [
        EncryptedSessionExchange(
            interaction_id=uuid4(), payload_ciphertext=old_payload, response_ciphertext=None
        )
        for _ in range(5)
    ]
    monkeypatch.setattr(processor_module, "TelegramInteractionsRepository", lambda _: repo)
    monkeypatch.setattr(processor_module, "LlmUsageRepository", lambda _: usage_repo)
    summarizer = AsyncMock()
    summarizer.summarize.return_value = SessionSummaryOutcome(
        summary_text=None, status="failed", error_class="AgentRunError"
    )
    processor = _compaction_processor(
        session=session, cipher=cipher, summarizer=summarizer, context_compaction_enabled=True
    )

    await processor._run_agent(accepted)

    processor._agent_runner.run.assert_awaited_once()  # type: ignore[attr-defined]
    kwargs = processor._agent_runner.run.await_args.kwargs  # type: ignore[attr-defined]
    assert kwargs["compaction_summary"] is None
    assert kwargs["reduced_history_runs"] is None
