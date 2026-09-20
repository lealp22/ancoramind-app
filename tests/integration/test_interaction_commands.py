"""PostgreSQL integration tests for deterministic commands and sessions (BL-28)."""

from __future__ import annotations

from uuid import UUID

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.interactions.commands import NEW_SESSION_REPLY
from src.domain.interactions.models import (
    TelegramDeliveryCreate,
    TelegramInteractionCreate,
)
from src.domain.interactions.payloads import TelegramPayloadCipher
from src.domain.interactions.processor import InteractionProcessor
from src.repositories.database import get_session
from src.repositories.interactions import TelegramInteractionsRepository

pytestmark = pytest.mark.integration


class FakeRunner:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def run(self, input_text: str, **kwargs: object) -> str:
        self.calls.append({"input_text": input_text, **kwargs})
        return "Respuesta del agente"


class FakeSender:
    def __init__(self) -> None:
        self.calls: list[tuple[int, str]] = []
        self.next_message_id = 900

    async def send_text(self, chat_id: int, text: str) -> int:
        self.calls.append((chat_id, text))
        self.next_message_id += 1
        return self.next_message_id

    async def send_typing(self, chat_id: int) -> None:
        return None


def _cipher() -> TelegramPayloadCipher:
    return TelegramPayloadCipher(Fernet.generate_key().decode("ascii"), key_version=1)


async def _accepted_interaction(
    session: AsyncSession,
    cipher: TelegramPayloadCipher,
    *,
    update_id: int,
    text: str,
) -> UUID:
    encrypted = cipher.encrypt({"update_id": update_id, "text": text})
    result = await TelegramInteractionsRepository(session).admit(
        TelegramInteractionCreate(
            bot_id=61,
            telegram_update_id=update_id,
            telegram_message_id=update_id + 1,
            chat_id=99,
            telegram_user_id=100,
            update_type="message",
            payload_ciphertext=encrypted.ciphertext,
            payload_key_version=encrypted.key_version,
            payload_fingerprint=encrypted.fingerprint,
        ),
        TelegramDeliveryCreate(railway_request_id=f"delivery-{update_id}", http_status=200),
    )
    return result.interaction.id


async def test_new_command_replies_durably_without_an_agent_run(
    session: AsyncSession,
) -> None:
    cipher = _cipher()
    await _accepted_interaction(session, cipher, update_id=701, text="/new")
    runner = FakeRunner()
    sender = FakeSender()
    processor = InteractionProcessor(
        session_factory=get_session,
        payload_cipher=cipher,
        agent_runner=runner,
        sender=sender,
    )

    assert await processor.run_once() == 1

    row = (
        await session.execute(
            text("""
                SELECT status, agno_run_id, agno_session_id, payload_ciphertext, error_class
                FROM ancora.telegram_interactions
                WHERE telegram_update_id = 701
            """)
        )
    ).one()
    assert row.status == "completed"
    assert row.agno_run_id is None
    assert row.agno_session_id == "tg:ancoramind:99:1"
    assert row.payload_ciphertext is None
    assert row.error_class is None
    assert runner.calls == []
    assert sender.calls == [(99, NEW_SESSION_REPLY)]

    responses = (
        await session.execute(
            text("""
                SELECT response_kind, status, chunk_count, content_ciphertext
                FROM ancora.logical_responses
                WHERE interaction_id = (
                    SELECT id FROM ancora.telegram_interactions WHERE telegram_update_id = 701
                )
            """)
        )
    ).all()
    assert [(item.response_kind, item.status, item.chunk_count) for item in responses] == [
        ("agent_final", "completed", 1)
    ]
    assert responses[0].content_ciphertext is not None


async def test_following_message_uses_the_session_opened_by_new(session: AsyncSession) -> None:
    cipher = _cipher()
    await _accepted_interaction(session, cipher, update_id=711, text="/new")
    await _accepted_interaction(session, cipher, update_id=712, text="¿seguimos?")
    runner = FakeRunner()
    processor = InteractionProcessor(
        session_factory=get_session,
        payload_cipher=cipher,
        agent_runner=runner,
        sender=FakeSender(),
    )

    assert await processor.run_once() == 2

    assert [call["session_id"] for call in runner.calls] == ["tg:ancoramind:99:1"]
    assert runner.calls[0]["input_text"] == "¿seguimos?"


async def test_command_reply_is_claimed_only_once(session: AsyncSession) -> None:
    cipher = _cipher()
    interaction_id = await _accepted_interaction(session, cipher, update_id=721, text="/help")
    repository = TelegramInteractionsRepository(session)
    encrypted = cipher.encrypt({"content": "respuesta"})

    first = await repository.claim_command_reply(
        interaction_id,
        agno_session_id=None,
        content_ciphertext=encrypted.ciphertext,
        content_key_version=encrypted.key_version,
        content_length=8,
        chunk_count=1,
    )
    second = await repository.claim_command_reply(
        interaction_id,
        agno_session_id=None,
        content_ciphertext=encrypted.ciphertext,
        content_key_version=encrypted.key_version,
        content_length=8,
        chunk_count=1,
    )

    assert first is not None
    assert second is None
    total = (
        await session.execute(
            text("""
                SELECT count(*) AS total
                FROM ancora.logical_responses
                WHERE interaction_id = :interaction_id
            """),
            {"interaction_id": interaction_id},
        )
    ).one()
    assert total.total == 1


async def test_current_session_id_tracks_the_ledger(session: AsyncSession) -> None:
    repository = TelegramInteractionsRepository(session)
    assert await repository.current_session_id(99) is None

    cipher = _cipher()
    await _accepted_interaction(session, cipher, update_id=731, text="hola")
    processor = InteractionProcessor(
        session_factory=get_session,
        payload_cipher=cipher,
        agent_runner=FakeRunner(),
        sender=FakeSender(),
    )
    await processor.run_once()

    assert await repository.current_session_id(99) == "tg:ancoramind:99"
    assert await repository.current_session_id(1234) is None
