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
from src.domain.interactions.models import InteractionStatus, TelegramInteraction
from src.domain.interactions.outbox import split_telegram_message
from src.domain.interactions.payloads import TelegramPayloadCipher
from src.domain.interactions.processor import InteractionProcessor, TelegramSendError
from src.repositories.interactions import TelegramInteractionsRepository


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
    sender.send_text.assert_not_awaited()
    repo.update_status.assert_awaited_once_with(
        accepted.id,
        InteractionStatus.FAILED_AMBIGUOUS,
        error_class="AgentRunError",
        error_detail_code="agent_run_failed_after_claim",
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
        ) -> str:
            assert input_text == "hola"
            assert user_id == "5"
            assert session_id == "tg:ancoramind:4"
            assert run_id
            assert correlation_id == accepted.id
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
