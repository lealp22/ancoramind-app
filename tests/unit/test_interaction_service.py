"""Unit tests for Telegram interaction ledger domain service."""

from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from cryptography.fernet import Fernet

from src.domain.interactions.models import InteractionStatus
from src.domain.interactions.payloads import TelegramPayloadCipher
from src.domain.interactions.service import TelegramInteractionService
from src.repositories.interactions import TelegramInteractionsRepository


@pytest.fixture
def repository() -> AsyncMock:
    return AsyncMock(spec=TelegramInteractionsRepository)


@pytest.fixture
def service(repository: AsyncMock) -> TelegramInteractionService:
    return TelegramInteractionService(
        repository,
        TelegramPayloadCipher(Fernet.generate_key().decode("ascii"), key_version=7),
    )


async def test_record_accepted_update_encrypts_before_repository_call(
    service: TelegramInteractionService,
    repository: AsyncMock,
) -> None:
    await service.record_accepted_update(
        bot_id=111,
        railway_request_id="railway-request-1",
        update={
            "update_id": 222,
            "message": {
                "message_id": 333,
                "chat": {"id": 444},
                "from": {"id": 555},
                "text": "mensaje personal",
            },
        },
    )

    interaction, delivery = repository.admit.await_args.args
    assert interaction.bot_id == 111
    assert interaction.telegram_update_id == 222
    assert interaction.payload_key_version == 7
    assert interaction.payload_ciphertext is not None
    assert b"mensaje personal" not in interaction.payload_ciphertext
    assert delivery.railway_request_id == "railway-request-1"
    assert delivery.delivery_status == "durable"


async def test_mark_terminal_rejects_non_terminal_status(
    service: TelegramInteractionService,
    repository: AsyncMock,
) -> None:
    with pytest.raises(ValueError, match="terminal"):
        await service.mark_terminal(uuid4(), InteractionStatus.AGENT_STARTED)

    repository.update_status.assert_not_awaited()


async def test_mark_terminal_delegates_terminal_state(
    service: TelegramInteractionService,
    repository: AsyncMock,
) -> None:
    correlation_id = uuid4()
    await service.mark_terminal(
        correlation_id,
        InteractionStatus.FAILED_AMBIGUOUS,
        error_class="TimeoutError",
        error_detail_code="agent_crash",
    )

    repository.update_status.assert_awaited_once_with(
        correlation_id,
        InteractionStatus.FAILED_AMBIGUOUS,
        error_class="TimeoutError",
        error_detail_code="agent_crash",
    )
