"""PostgreSQL integration tests for T5 processor, recovery and response outbox."""

from __future__ import annotations

from uuid import UUID

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

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
    def __init__(self, content: str = "Respuesta final") -> None:
        self.content = content
        self.calls: list[dict[str, object]] = []
        self.error: Exception | None = None

    async def run(self, input_text: str, **kwargs: object) -> str:
        self.calls.append({"input_text": input_text, **kwargs})
        if self.error:
            raise self.error
        return self.content


class FakeSender:
    def __init__(self) -> None:
        self.calls: list[tuple[int, str]] = []
        self.next_message_id = 100

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
    update_id: int,
) -> UUID:
    encrypted = cipher.encrypt({"update_id": update_id, "text": "Hola procesador"})
    result = await TelegramInteractionsRepository(session).admit(
        TelegramInteractionCreate(
            bot_id=41,
            telegram_update_id=update_id,
            telegram_message_id=update_id + 1,
            chat_id=77,
            telegram_user_id=88,
            update_type="message",
            payload_ciphertext=encrypted.ciphertext,
            payload_key_version=encrypted.key_version,
            payload_fingerprint=encrypted.fingerprint,
        ),
        TelegramDeliveryCreate(railway_request_id=f"delivery-{update_id}", http_status=200),
    )
    return result.interaction.id


async def test_processor_persists_outbox_before_confirmed_chunk_delivery(
    session: AsyncSession,
) -> None:
    cipher = _cipher()
    interaction_id = await _accepted_interaction(session, cipher, update_id=501)
    runner = FakeRunner(content="respuesta " * 600)
    sender = FakeSender()
    processor = InteractionProcessor(
        session_factory=get_session,
        payload_cipher=cipher,
        agent_runner=runner,
        sender=sender,
        global_concurrency=2,
    )

    assert await processor.run_once() == 1

    interaction = (
        await session.execute(
            text("""
                SELECT status, agno_run_id, agno_session_id, payload_ciphertext
                FROM ancora.telegram_interactions
                WHERE id = :id
            """),
            {"id": interaction_id},
        )
    ).one()
    assert interaction.status == "completed"
    assert interaction.agno_run_id is not None
    assert interaction.agno_session_id == "tg:ancoramind:77"
    assert interaction.payload_ciphertext is None
    response = (
        await session.execute(
            text("""
                SELECT id, status, content_ciphertext, content_key_version, chunk_count
                FROM ancora.logical_responses
                WHERE interaction_id = :id
            """),
            {"id": interaction_id},
        )
    ).one()
    assert response.status == "completed"
    assert response.content_ciphertext is not None
    assert response.content_key_version == 1
    assert b"respuesta" not in response.content_ciphertext
    assert response.chunk_count == len(sender.calls)
    deliveries = (
        await session.execute(
            text("""
                SELECT status, telegram_message_id
                FROM ancora.telegram_response_deliveries
                WHERE logical_response_id = :id
                ORDER BY chunk_index
            """),
            {"id": response.id},
        )
    ).fetchall()
    assert all(row.status == "completed" for row in deliveries)
    assert all(row.telegram_message_id is not None for row in deliveries)
    assert len(runner.calls) == 1


async def test_processor_does_not_replay_agent_after_post_claim_failure(
    session: AsyncSession,
) -> None:
    cipher = _cipher()
    interaction_id = await _accepted_interaction(session, cipher, update_id=502)
    runner = FakeRunner()
    runner.error = RuntimeError("agent failure")
    sender = FakeSender()
    processor = InteractionProcessor(
        session_factory=get_session,
        payload_cipher=cipher,
        agent_runner=runner,
        sender=sender,
    )

    assert await processor.run_once() == 1
    assert await processor.run_once() == 0

    row = (
        await session.execute(
            text("""
                SELECT status, error_class, error_detail_code
                FROM ancora.telegram_interactions
                WHERE id = :id
            """),
            {"id": interaction_id},
        )
    ).one()
    assert row.status == "failed_ambiguous"
    assert row.error_class == "AgentRunError"
    assert row.error_detail_code == "agent_run_failed_after_claim"
    assert len(runner.calls) == 1
    assert sender.calls == []


async def test_recovery_marks_inflight_ambiguous_but_delivers_response_ready(
    session: AsyncSession,
) -> None:
    cipher = _cipher()
    agent_started_id = await _accepted_interaction(session, cipher, update_id=503)
    delivery_started_id = await _accepted_interaction(session, cipher, update_id=505)
    response_ready_id = await _accepted_interaction(session, cipher, update_id=504)
    repository = TelegramInteractionsRepository(session)
    assert await repository.claim_agent_start_with_run_id(
        agent_started_id,
        "run-503",
        "tg:ancoramind:77",
    )
    assert await repository.claim_agent_start_with_run_id(
        delivery_started_id,
        "run-505",
        "tg:ancoramind:77",
    )
    assert await repository.claim_agent_start_with_run_id(
        response_ready_id, "run-504", "tg:ancoramind:77"
    )
    response_payload = cipher.encrypt({"content": "respuesta recuperable"})
    assert await repository.persist_response_ready(
        response_ready_id,
        content_ciphertext=response_payload.ciphertext,
        content_key_version=response_payload.key_version,
        content_length=len("respuesta recuperable"),
        chunk_count=1,
    )
    delivery_payload = cipher.encrypt({"content": "respuesta no reenviable"})
    assert await repository.persist_response_ready(
        delivery_started_id,
        content_ciphertext=delivery_payload.ciphertext,
        content_key_version=delivery_payload.key_version,
        content_length=len("respuesta no reenviable"),
        chunk_count=1,
    )
    assert await repository.claim_delivery_start(delivery_started_id)

    runner = FakeRunner()
    sender = FakeSender()
    processor = InteractionProcessor(
        session_factory=get_session,
        payload_cipher=cipher,
        agent_runner=runner,
        sender=sender,
    )

    assert await processor.recover_once() == 2
    assert await processor.run_once() == 1

    rows = (
        await session.execute(
            text("""
                SELECT id, status, error_detail_code
                FROM ancora.telegram_interactions
                WHERE id IN (:agent_started_id, :response_ready_id, :delivery_started_id)
                ORDER BY telegram_update_id
            """),
            {
                "agent_started_id": agent_started_id,
                "response_ready_id": response_ready_id,
                "delivery_started_id": delivery_started_id,
            },
        )
    ).fetchall()
    assert rows[0].id == agent_started_id
    assert rows[0].status == "failed_ambiguous"
    assert rows[0].error_detail_code == "restart_after_agent_started"
    assert rows[1].id == response_ready_id
    assert rows[1].status == "completed"
    assert rows[2].id == delivery_started_id
    assert rows[2].status == "failed_ambiguous"
    assert rows[2].error_detail_code == "restart_during_delivery"
    assert runner.calls == []
    assert sender.calls == [(77, "respuesta recuperable")]
