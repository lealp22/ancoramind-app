"""PostgreSQL integration tests for atomic governed Telegram pairing redemption."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.interactions.pairing import (
    PairingRedemptionStatus,
    PairingRequestStatus,
    hash_pairing_code,
)
from src.repositories.database import get_session
from src.repositories.pairing import TelegramPairingRepository

pytestmark = pytest.mark.integration

PEPPER = "integration-pairing-pepper"
PAIRING_REQUEST_COUNT_SQL = text("""
    SELECT count(*) AS total
    FROM ancora.telegram_pairing_requests
""")


async def _create_invitation(
    session: AsyncSession,
    *,
    code: str,
    max_uses: int = 1,
    expires_at: datetime | None = None,
):
    return await TelegramPairingRepository(session).create_invitation(
        code_hash=hash_pairing_code(code, PEPPER),
        max_uses=max_uses,
        expires_at=expires_at or datetime.now(tz=UTC) + timedelta(hours=1),
        created_by="integration-operator",
        reason="integration test",
    )


async def test_redemption_creates_one_pending_request_and_consumes_capacity(
    session: AsyncSession,
) -> None:
    invitation = await _create_invitation(session, code="valid-code")
    repository = TelegramPairingRepository(session)

    redemption = await repository.redeem_invitation(
        code_hash=hash_pairing_code("valid-code", PEPPER), telegram_user_id=41
    )

    assert redemption.status is PairingRedemptionStatus.PENDING
    assert redemption.request is not None
    assert redemption.request.status is PairingRequestStatus.PENDING
    row = (
        await session.execute(
            text("""
                SELECT status, use_count
                FROM ancora.telegram_pairing_invitations
                WHERE id = :id
            """),
            {"id": invitation.id},
        )
    ).one()
    assert (row.status, row.use_count) == ("exhausted", 1)


async def test_replay_and_second_user_cannot_consume_a_single_use_invitation(
    session: AsyncSession,
) -> None:
    await _create_invitation(session, code="single-use")
    repository = TelegramPairingRepository(session)
    code_hash = hash_pairing_code("single-use", PEPPER)

    first = await repository.redeem_invitation(code_hash=code_hash, telegram_user_id=51)
    replay = await repository.redeem_invitation(code_hash=code_hash, telegram_user_id=51)
    second_user = await repository.redeem_invitation(code_hash=code_hash, telegram_user_id=52)

    assert first.status is PairingRedemptionStatus.PENDING
    assert replay.status is PairingRedemptionStatus.ALREADY_PENDING
    assert second_user.status is PairingRedemptionStatus.EXHAUSTED


async def test_expired_or_invalid_code_creates_no_request(session: AsyncSession) -> None:
    await _create_invitation(
        session,
        code="expired-code",
        expires_at=datetime.now(tz=UTC) - timedelta(seconds=1),
    )
    repository = TelegramPairingRepository(session)

    expired = await repository.redeem_invitation(
        code_hash=hash_pairing_code("expired-code", PEPPER), telegram_user_id=61
    )
    invalid = await repository.redeem_invitation(
        code_hash=hash_pairing_code("unknown-code", PEPPER), telegram_user_id=62
    )

    assert expired.status is PairingRedemptionStatus.EXPIRED
    assert invalid.status is PairingRedemptionStatus.INVALID
    total = (await session.execute(PAIRING_REQUEST_COUNT_SQL)).one()
    assert total.total == 0


async def test_concurrent_redemption_consumes_one_capacity_unit(session: AsyncSession) -> None:
    await _create_invitation(session, code="race-code")
    code_hash = hash_pairing_code("race-code", PEPPER)

    async def redeem(user_id: int) -> PairingRedemptionStatus:
        other_session = await get_session()
        try:
            result = await TelegramPairingRepository(other_session).redeem_invitation(
                code_hash=code_hash, telegram_user_id=user_id
            )
            return result.status
        finally:
            await other_session.close()

    outcomes = await asyncio.gather(redeem(71), redeem(72))

    assert sorted(outcomes) == sorted(
        [PairingRedemptionStatus.EXHAUSTED, PairingRedemptionStatus.PENDING]
    )
    total = (await session.execute(PAIRING_REQUEST_COUNT_SQL)).one()
    assert total.total == 1
