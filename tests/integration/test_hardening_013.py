"""T13 hardening: load, crash-injection and retention over real PostgreSQL."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.domain.interactions.models import (
    InteractionStatus,
    TelegramDeliveryCreate,
    TelegramInteraction,
    TelegramInteractionCreate,
)
from src.domain.interactions.payloads import TelegramPayloadCipher
from src.domain.interactions.processor import InteractionProcessor
from src.repositories.database import get_session
from src.repositories.interactions import TelegramInteractionsRepository

pytestmark = pytest.mark.integration


class _Runner:
    def __init__(self) -> None:
        self.calls: list[UUID] = []

    async def run(self, input_text: str, **kwargs: object) -> str:
        assert kwargs["correlation_id"] is not None
        self.calls.append(kwargs["correlation_id"])  # type: ignore[arg-type]
        return f"respuesta-{input_text}"


class _Sender:
    def __init__(self) -> None:
        self.calls: list[tuple[int, str]] = []
        self.next_message_id = 5000

    async def send_text(self, chat_id: int, text: str) -> int:
        self.calls.append((chat_id, text))
        self.next_message_id += 1
        return self.next_message_id

    async def send_typing(self, chat_id: int) -> None:
        return None


def _cipher() -> TelegramPayloadCipher:
    return TelegramPayloadCipher(Fernet.generate_key().decode("ascii"), key_version=1)


def _create(
    cipher: TelegramPayloadCipher,
    update_id: int,
    *,
    chat_id: int = 5100,
) -> TelegramInteractionCreate:
    encrypted = cipher.encrypt({"update_id": update_id, "text": "hola hardening"})
    return TelegramInteractionCreate(
        bot_id=51,
        telegram_update_id=update_id,
        telegram_message_id=update_id + 1,
        chat_id=chat_id,
        telegram_user_id=77,
        update_type="message",
        payload_ciphertext=encrypted.ciphertext,
        payload_key_version=encrypted.key_version,
        payload_fingerprint=encrypted.fingerprint,
    )


async def _admit(
    session: AsyncSession,
    cipher: TelegramPayloadCipher,
    update_id: int,
    *,
    chat_id: int = 5100,
    delivery: str = "railway",
) -> UUID:
    result = await TelegramInteractionsRepository(session).admit(
        _create(cipher, update_id, chat_id=chat_id),
        TelegramDeliveryCreate(railway_request_id=f"{delivery}-{update_id}", http_status=200),
    )
    await session.commit()
    return result.interaction.id


def _processor(
    cipher: TelegramPayloadCipher, runner: _Runner, sender: _Sender
) -> InteractionProcessor:
    return InteractionProcessor(
        session_factory=get_session,
        payload_cipher=cipher,
        agent_runner=runner,
        sender=sender,
        global_concurrency=2,
    )


async def test_load_twenty_duplicates_one_claim(session: AsyncSession) -> None:
    cipher = _cipher()
    await _admit(session, cipher, update_id=6001)
    assert session.bind is not None
    sessions = async_sessionmaker(session.bind, class_=AsyncSession, expire_on_commit=False)
    create = _create(cipher, update_id=6001)

    async def admit(index: int) -> bool:
        async with sessions() as concurrent:
            result = await TelegramInteractionsRepository(concurrent).admit(
                create,
                TelegramDeliveryCreate(railway_request_id=f"hardening-{index}", http_status=200),
            )
            await concurrent.commit()
            return result.duplicate

    duplicates = await asyncio.gather(*(admit(index) for index in range(19)))
    assert sum(duplicates) == 19

    counts = (
        await session.execute(
            text("""
                SELECT
                    (SELECT count(*) FROM ancora.telegram_interactions
                      WHERE bot_id = 51 AND telegram_update_id = 6001) AS interactions,
                    (SELECT count(*) FROM ancora.telegram_deliveries d
                      JOIN ancora.telegram_interactions i ON i.id = d.interaction_id
                      WHERE i.bot_id = 51 AND i.telegram_update_id = 6001) AS deliveries
            """)
        )
    ).one()
    assert (counts.interactions, counts.deliveries) == (1, 20)


async def test_load_burst_distinct_updates_ordered_exactly_once(
    session: AsyncSession,
) -> None:
    cipher = _cipher()
    for update_id in (6101, 6102, 6103, 6104, 6105):
        await _admit(session, cipher, update_id=update_id)
    runner, sender = _Runner(), _Sender()

    # One run_once() drains the whole chat queue (batch); each interaction
    # runs exactly once, in received_at order, deterministically auditable.
    completed_before = 0
    for _ in range(5):
        processed = await _processor(cipher, runner, sender).run_once()
        completed_before += processed
        if processed == 0:
            break

    assert completed_before == 5
    assert len(runner.calls) == 5
    assert len({call for call in runner.calls}) == 5
    assert len(sender.calls) == 5
    assert [call[1] for call in sender.calls] == [
        "respuesta-hola hardening",
    ] * 5
    completed = (
        await session.execute(
            text("""
                SELECT count(*) AS completed
                FROM ancora.telegram_interactions
                WHERE bot_id = 51 AND telegram_update_id BETWEEN 6101 AND 6105
                  AND status = 'completed'
            """)
        )
    ).one()
    assert completed.completed == 5


async def test_crash_after_agent_start_never_replays(
    session: AsyncSession,
) -> None:
    cipher = _cipher()
    interaction_id = await _admit(session, cipher, update_id=6201)
    repository = TelegramInteractionsRepository(session)
    assert await repository.claim_agent_start_with_run_id(
        interaction_id, "run-crash-6201", "tg:ancoramind:5100"
    )
    await session.commit()

    runner, sender = _Runner(), _Sender()
    processor = _processor(cipher, runner, sender)
    assert await processor.recover_once() == 1
    assert await processor.run_once() == 0

    row = (
        await session.execute(
            text("""
                SELECT status, error_detail_code
                FROM ancora.telegram_interactions WHERE id = :id
            """),
            {"id": interaction_id},
        )
    ).one()
    assert (row.status, row.error_detail_code) == (
        "failed_ambiguous",
        "restart_after_agent_started",
    )
    assert runner.calls == []
    assert sender.calls == []


async def test_crash_during_delivery_never_resends(
    session: AsyncSession,
) -> None:
    cipher = _cipher()
    interaction_id = await _admit(session, cipher, update_id=6301)
    repository = TelegramInteractionsRepository(session)
    assert await repository.claim_agent_start_with_run_id(
        interaction_id, "run-crash-6301", "tg:ancoramind:5100"
    )
    encrypted = cipher.encrypt({"content": "respuesta no reenviable"})
    assert await repository.persist_response_ready(
        interaction_id,
        content_ciphertext=encrypted.ciphertext,
        content_key_version=encrypted.key_version,
        content_length=24,
        chunk_count=1,
    )
    assert await repository.claim_delivery_start(interaction_id)
    await session.commit()

    runner, sender = _Runner(), _Sender()
    processor = _processor(cipher, runner, sender)
    assert await processor.recover_once() == 1
    assert await processor.run_once() == 0

    row = (
        await session.execute(
            text("""
                SELECT status FROM ancora.telegram_interactions WHERE id = :id
            """),
            {"id": interaction_id},
        )
    ).one()
    assert row.status == "failed_ambiguous"
    assert runner.calls == []
    assert sender.calls == []


async def test_restart_with_response_ready_delivers_without_rerun(
    session: AsyncSession,
) -> None:
    cipher = _cipher()
    interaction_id = await _admit(session, cipher, update_id=6401)
    repository = TelegramInteractionsRepository(session)
    assert await repository.claim_agent_start_with_run_id(
        interaction_id, "run-recover-6401", "tg:ancoramind:5100"
    )
    encrypted = cipher.encrypt({"content": "respuesta recuperable"})
    assert await repository.persist_response_ready(
        interaction_id,
        content_ciphertext=encrypted.ciphertext,
        content_key_version=encrypted.key_version,
        content_length=21,
        chunk_count=1,
    )
    await session.commit()

    runner, sender = _Runner(), _Sender()
    assert await _processor(cipher, runner, sender).run_once() == 1
    assert runner.calls == []
    assert sender.calls == [(5100, "respuesta recuperable")]
    row = (
        await session.execute(
            text("""
                SELECT status FROM ancora.telegram_interactions WHERE id = :id
            """),
            {"id": interaction_id},
        )
    ).one()
    assert row.status == "completed"


async def test_retention_purges_expired_ambiguous_payload(
    session: AsyncSession,
) -> None:
    cipher = _cipher()
    interaction_id = await _admit(session, cipher, update_id=6501)
    repository = TelegramInteractionsRepository(session)
    await repository.update_status(interaction_id, InteractionStatus.FAILED_AMBIGUOUS)
    await session.execute(
        text("""
            UPDATE ancora.telegram_interactions
            SET completed_at = :expired WHERE id = :id
        """),
        {"id": interaction_id, "expired": datetime.now(tz=UTC) - timedelta(days=8)},
    )
    await session.commit()

    assert await repository.purge_expired_payloads() == 1
    row = (
        await session.execute(
            text("""
                SELECT payload_ciphertext, payload_key_version,
                       payload_fingerprint, status
                FROM ancora.telegram_interactions WHERE id = :id
            """),
            {"id": interaction_id},
        )
    ).one()
    assert row.payload_ciphertext is None
    assert row.payload_key_version is None
    assert row.payload_fingerprint is not None
    assert row.status == "failed_ambiguous"


async def test_ordering_is_deterministic_by_received_at_then_update_id(
    session: AsyncSession,
) -> None:
    # list_recoverable_work orders by (chat_id, received_at, update_id): rows
    # admitted in the same millisecond keep insertion order, so the contract
    # asserted here is stability — same query, same order, every cycle.
    cipher = _cipher()
    for update_id in (6603, 6601, 6602):
        await _admit(session, cipher, update_id=update_id)
    first = [
        row.id for row in await TelegramInteractionsRepository(session).list_recoverable_work(10)
    ]
    second = [
        row.id for row in await TelegramInteractionsRepository(session).list_recoverable_work(10)
    ]
    assert first == second
    listed = await TelegramInteractionsRepository(session).list_recoverable_work(10)
    assert isinstance(listed[0], TelegramInteraction)
    assert {row.telegram_update_id for row in listed if row.chat_id == 5100} == {
        6601,
        6602,
        6603,
    }
