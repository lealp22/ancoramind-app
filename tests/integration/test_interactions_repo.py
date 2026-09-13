"""Integration tests for durable Telegram interaction ledger (specs/013 T3)."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.domain.interactions.models import (
    InteractionStatus,
    TelegramAdmissionResult,
    TelegramDeliveryCreate,
    TelegramInteraction,
    TelegramInteractionCreate,
)
from src.domain.interactions.payloads import TelegramPayloadCipher
from src.domain.interactions.service import TelegramInteractionService
from src.repositories.interactions import TelegramInteractionsRepository

pytestmark = pytest.mark.integration


def _cipher() -> TelegramPayloadCipher:
    return TelegramPayloadCipher(Fernet.generate_key().decode("ascii"), key_version=1)


def _interaction() -> TelegramInteractionCreate:
    encrypted = _cipher().encrypt({"update_id": 9001, "text": "contenido personal"})
    return TelegramInteractionCreate(
        bot_id=8001,
        telegram_update_id=9001,
        telegram_message_id=1001,
        chat_id=2001,
        telegram_user_id=3001,
        update_type="message",
        payload_ciphertext=encrypted.ciphertext,
        payload_key_version=encrypted.key_version,
        payload_fingerprint=encrypted.fingerprint,
    )


async def test_admit_is_idempotent_and_audits_duplicate_delivery(session: AsyncSession) -> None:
    repository = TelegramInteractionsRepository(session)
    interaction = _interaction()

    first = await repository.admit(
        interaction,
        TelegramDeliveryCreate(railway_request_id="delivery-a", http_status=200),
    )
    duplicate = await repository.admit(
        interaction,
        TelegramDeliveryCreate(railway_request_id="delivery-b", http_status=200),
    )

    assert first.duplicate is False
    assert duplicate.duplicate is True
    assert duplicate.interaction.correlation_id == first.interaction.correlation_id

    rows = (
        await session.execute(
            text("""
                SELECT duplicate, railway_request_id
                FROM ancora.telegram_deliveries
                WHERE interaction_id = :interaction_id
                ORDER BY received_at, id
            """),
            {"interaction_id": first.interaction.id},
        )
    ).fetchall()
    assert [(row.duplicate, row.railway_request_id) for row in rows] == [
        (False, "delivery-a"),
        (True, "delivery-b"),
    ]


async def test_twenty_concurrent_deliveries_create_one_interaction_and_one_claim(
    session: AsyncSession,
) -> None:
    assert session.bind is not None
    sessions = async_sessionmaker(session.bind, class_=AsyncSession, expire_on_commit=False)
    interaction = _interaction()

    async def admit(index: int) -> TelegramAdmissionResult:
        async with sessions() as concurrent_session:
            return await TelegramInteractionsRepository(concurrent_session).admit(
                interaction,
                TelegramDeliveryCreate(railway_request_id=f"delivery-{index}", http_status=200),
            )

    admissions = await asyncio.gather(*(admit(index) for index in range(20)))

    assert sum(not admission.duplicate for admission in admissions) == 1
    correlation_ids = {admission.interaction.correlation_id for admission in admissions}
    assert len(correlation_ids) == 1
    correlation_id = correlation_ids.pop()

    async def claim() -> TelegramInteraction | None:
        async with sessions() as concurrent_session:
            return await TelegramInteractionsRepository(concurrent_session).claim_agent_start(
                correlation_id
            )

    claims: list[TelegramInteraction | None] = list(
        await asyncio.gather(*(claim() for _ in range(20)))
    )
    assert sum(claim is not None for claim in claims) == 1

    counts = (
        await session.execute(
            text("""
                SELECT
                    (SELECT count(*) FROM ancora.telegram_interactions
                     WHERE bot_id = :bot_id AND telegram_update_id = :update_id) AS interactions,
                    (SELECT count(*) FROM ancora.telegram_deliveries
                     WHERE interaction_id = :interaction_id) AS deliveries
            """),
            {
                "bot_id": interaction.bot_id,
                "update_id": interaction.telegram_update_id,
                "interaction_id": correlation_id,
            },
        )
    ).one()
    assert counts.interactions == 1
    assert counts.deliveries == 20


async def test_terminal_status_clears_normal_payload_and_retention_purges_ambiguous(
    session: AsyncSession,
) -> None:
    repository = TelegramInteractionsRepository(session)
    first = await repository.admit(_interaction(), TelegramDeliveryCreate())

    completed = await repository.update_status(first.interaction.id, InteractionStatus.COMPLETED)
    assert completed is not None
    assert completed.payload_ciphertext is None
    assert completed.payload_key_version is None

    encrypted = _cipher().encrypt({"update_id": 9002, "text": "investigation payload"})
    ambiguous = await repository.admit(
        TelegramInteractionCreate(
            bot_id=8001,
            telegram_update_id=9002,
            update_type="message",
            payload_ciphertext=encrypted.ciphertext,
            payload_key_version=encrypted.key_version,
            payload_fingerprint=encrypted.fingerprint,
        ),
        TelegramDeliveryCreate(),
    )
    retained = await repository.update_status(
        ambiguous.interaction.id,
        InteractionStatus.FAILED_AMBIGUOUS,
    )
    assert retained is not None
    assert retained.payload_ciphertext is not None

    old_completion = datetime.now(tz=UTC) - timedelta(days=8)
    await session.execute(
        text("""
            UPDATE ancora.telegram_interactions
            SET completed_at = :completed_at
            WHERE id = :id
        """),
        {"id": ambiguous.interaction.id, "completed_at": old_completion},
    )
    await session.commit()

    assert await repository.purge_expired_payloads() == 1
    row = (
        await session.execute(
            text("""
                SELECT payload_ciphertext, payload_key_version, payload_fingerprint
                FROM ancora.telegram_interactions
                WHERE id = :id
            """),
            {"id": ambiguous.interaction.id},
        )
    ).one()
    assert row.payload_ciphertext is None
    assert row.payload_key_version is None
    assert row.payload_fingerprint == encrypted.fingerprint


async def test_service_persists_ciphertext_not_plaintext(session: AsyncSession) -> None:
    cipher = _cipher()
    service = TelegramInteractionService(TelegramInteractionsRepository(session), cipher)

    result = await service.record_accepted_update(
        bot_id=81,
        railway_request_id="railway-81",
        update={
            "update_id": 91,
            "message": {
                "message_id": 101,
                "chat": {"id": 111},
                "from": {"id": 121},
                "text": "mensaje que no debe almacenarse en claro",
            },
        },
    )

    row = (
        await session.execute(
            text("""
                SELECT payload_ciphertext, payload_fingerprint
                FROM ancora.telegram_interactions
                WHERE id = :id
            """),
            {"id": result.interaction.id},
        )
    ).one()
    assert row.payload_ciphertext is not None
    assert b"mensaje que no debe almacenarse en claro" not in row.payload_ciphertext
    assert row.payload_fingerprint is not None
