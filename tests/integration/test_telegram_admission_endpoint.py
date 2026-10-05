"""HTTP integration tests for the AncoraMind Telegram admission endpoint (T4)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from cryptography.fernet import Fernet
from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.agent.telegram_admission import install_telegram_admission_endpoint
from src.config import Settings
from src.domain.interactions.pairing import hash_pairing_code
from src.domain.interactions.payloads import TelegramPayloadCipher
from src.domain.interactions.processor import InteractionProcessor
from src.domain.interactions.service import PAIRING_AUTO_APPROVED_REPLY, PAIRING_PENDING_REPLY
from src.repositories.database import get_session
from src.repositories.pairing import TelegramPairingRepository

pytestmark = pytest.mark.integration


def _settings(**overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "telegram_admission_enabled": True,
        "telegram_token": "123456:token",
        "ancora_database_url": "postgresql+asyncpg://user:pass@localhost/db",
        "telegram_bot_id": 456,
        "telegram_webhook_secret_token": "webhook-secret",
        "telegram_payload_encryption_key": Fernet.generate_key().decode("ascii"),
        "allowed_telegram_user_ids": "999",
        "telegram_admission_user_burst": 5,
        "telegram_admission_burst_window_seconds": 10,
        "telegram_admission_user_requests_per_minute": 10,
        "telegram_admission_user_requests_per_hour": 120,
        "telegram_admission_pending_global": 20,
        "telegram_admission_queued_per_chat": 5,
    }
    values.update(overrides)
    return Settings(**values)


def _update(
    update_id: int,
    *,
    chat_type: str = "private",
    user_id: int = 999,
    chat_id: int = 333,
    text_value: str = "content that must not leave the ledger ciphertext",
) -> dict[str, Any]:
    return {
        "update_id": update_id,
        "message": {
            "message_id": update_id + 1,
            "chat": {"id": chat_id, "type": chat_type},
            "from": {"id": user_id},
            "text": text_value,
        },
    }


async def _post(
    app: FastAPI,
    payload: object,
    *,
    railway_request_id: str = "railway-request",
    secret: str = "webhook-secret",
) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.post(
            "/telegram/webhook",
            json=payload,
            headers={
                "x-telegram-bot-api-secret-token": secret,
                "x-railway-request-id": railway_request_id,
            },
        )


def _app(settings: Settings) -> FastAPI:
    app = FastAPI()
    install_telegram_admission_endpoint(app, settings, get_session)
    return app


class _Runner:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def run(self, input_text: str, **_: object) -> str:
        self.calls.append(input_text)
        return "unexpected agent response"


class _Sender:
    def __init__(self) -> None:
        self.calls: list[tuple[int, str]] = []

    async def send_text(self, chat_id: int, text_value: str) -> int:
        self.calls.append((chat_id, text_value))
        return 1

    async def send_typing(self, chat_id: int) -> None:
        return None


async def _create_pairing_invitation(
    session: AsyncSession, code: str, *, auto_approve: bool = False
) -> object:
    return await TelegramPairingRepository(session).create_invitation(
        code_hash=hash_pairing_code(code, "pairing-pepper"),
        max_uses=1,
        expires_at=datetime.now(tz=UTC) + timedelta(hours=1),
        created_by="integration-operator",
        reason="controlled evaluator",
        auto_approve=auto_approve,
    )


async def test_private_allowlisted_update_is_committed_before_200(session: AsyncSession) -> None:
    app = _app(_settings())

    response = await _post(app, _update(100), railway_request_id="railway-100")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "accepted"
    assert body["duplicate"] is False
    assert "content that must not leave" not in response.text
    row = (
        await session.execute(
            text("""
                SELECT status, railway_request_id, payload_ciphertext
                FROM ancora.telegram_interactions interaction
                JOIN ancora.telegram_deliveries delivery ON delivery.interaction_id = interaction.id
                WHERE interaction.id = :id
            """),
            {"id": body["correlation_id"]},
        )
    ).one()
    assert row.status == "accepted"
    assert row.railway_request_id == "railway-100"
    assert b"content that must not leave the ledger ciphertext" not in row.payload_ciphertext


@pytest.mark.parametrize(
    ("payload", "expected_code"),
    [
        (_update(101, chat_type="group"), "non_private_chat"),
        (_update(102, user_id=1000), "user_not_allowlisted"),
        ({"update_id": 103, "inline_query": {"id": "unsupported"}}, "unsupported_update"),
    ],
)
async def test_rejected_or_ignored_updates_commit_without_agent_execution(
    session: AsyncSession,
    payload: dict[str, Any],
    expected_code: str,
) -> None:
    app = _app(_settings())

    response = await _post(app, payload)

    assert response.status_code == 200
    row = (
        await session.execute(
            text("""
                SELECT status, error_detail_code, payload_ciphertext
                FROM ancora.telegram_interactions
                WHERE id = :id
            """),
            {"id": response.json()["correlation_id"]},
        )
    ).one()
    if expected_code == "unsupported_update":
        assert row.status == "ignored"
    else:
        assert row.status == "rejected"
    assert row.error_detail_code == expected_code
    assert row.payload_ciphertext is None


async def test_duplicate_is_durable_and_does_not_consume_rate_quota(session: AsyncSession) -> None:
    app = _app(_settings(telegram_admission_user_burst=1))

    first = await _post(app, _update(200), railway_request_id="railway-first")
    duplicate = await _post(app, _update(200), railway_request_id="railway-duplicate")
    limited = await _post(app, _update(201), railway_request_id="railway-limited")

    assert first.status_code == duplicate.status_code == limited.status_code == 200
    assert first.json()["status"] == "accepted"
    assert duplicate.json() == {
        "status": "accepted",
        "duplicate": True,
        "correlation_id": first.json()["correlation_id"],
    }
    assert limited.json()["status"] == "rejected"
    assert limited.json()["duplicate"] is False
    limited_row = (
        await session.execute(
            text("""
                SELECT error_detail_code, payload_ciphertext
                FROM ancora.telegram_interactions
                WHERE id = :id
            """),
            {"id": limited.json()["correlation_id"]},
        )
    ).one()
    assert limited_row.error_detail_code == "user_burst_exceeded"
    assert limited_row.payload_ciphertext is None
    deliveries = (
        await session.execute(
            text("""
                SELECT duplicate, railway_request_id
                FROM ancora.telegram_deliveries
                WHERE interaction_id = :id
                ORDER BY received_at, id
            """),
            {"id": first.json()["correlation_id"]},
        )
    ).fetchall()
    assert [(row.duplicate, row.railway_request_id) for row in deliveries] == [
        (False, "railway-first"),
        (True, "railway-duplicate"),
    ]


async def test_pending_global_capacity_rejects_new_update(session: AsyncSession) -> None:
    app = _app(_settings(telegram_admission_pending_global=1))

    accepted = await _post(app, _update(300, chat_id=300))
    rejected = await _post(app, _update(301, chat_id=301))

    assert accepted.json()["status"] == "accepted"
    assert rejected.json()["status"] == "rejected"
    row = (
        await session.execute(
            text("SELECT error_detail_code FROM ancora.telegram_interactions WHERE id = :id"),
            {"id": rejected.json()["correlation_id"]},
        )
    ).one()
    assert row.error_detail_code == "pending_global_capacity_exceeded"


@pytest.mark.parametrize(
    ("settings_override", "expected_code"),
    [
        ({"telegram_admission_user_requests_per_minute": 1}, "user_minute_limit_exceeded"),
        ({"telegram_admission_user_requests_per_hour": 1}, "user_hour_limit_exceeded"),
        ({"telegram_admission_queued_per_chat": 1}, "queued_per_chat_capacity_exceeded"),
    ],
)
async def test_admission_rejects_configured_user_or_chat_capacity(
    session: AsyncSession,
    settings_override: dict[str, Any],
    expected_code: str,
) -> None:
    app = _app(_settings(**settings_override))

    first = await _post(app, _update(400, chat_id=400))
    if expected_code == "queued_per_chat_capacity_exceeded":
        second = await _post(app, _update(401, chat_id=400))
    else:
        second = await _post(app, _update(401, chat_id=401))

    assert first.json()["status"] == "accepted"
    assert second.status_code == 200
    assert second.json()["status"] == "rejected"
    row = (
        await session.execute(
            text("SELECT error_detail_code FROM ancora.telegram_interactions WHERE id = :id"),
            {"id": second.json()["correlation_id"]},
        )
    ).one()
    assert row.error_detail_code == expected_code


async def test_private_pairing_uses_outbox_without_agent_or_raw_code_persistence(
    session: AsyncSession,
) -> None:
    code = "pairing-code-with-at-least-twenty-characters"
    await _create_pairing_invitation(session, code)
    settings = _settings(
        telegram_pairing_enabled=True,
        telegram_pairing_code_pepper="pairing-pepper",
    )
    app = _app(settings)

    response = await _post(
        app,
        _update(501, user_id=1501, text_value=f"/pair {code}"),
    )

    assert response.status_code == 200
    assert response.json()["status"] == "response_ready"
    interaction = (
        await session.execute(
            text("""
                SELECT status, payload_ciphertext
                FROM ancora.telegram_interactions
                WHERE id = :id
            """),
            {"id": response.json()["correlation_id"]},
        )
    ).one()
    assert interaction.status == "response_ready"
    assert code.encode() not in interaction.payload_ciphertext
    stored_response = (
        await session.execute(
            text("""
                SELECT content_ciphertext
                FROM ancora.logical_responses
                WHERE interaction_id = :id
            """),
            {"id": response.json()["correlation_id"]},
        )
    ).one()
    assert code.encode() not in stored_response.content_ciphertext

    runner = _Runner()
    sender = _Sender()
    processor = InteractionProcessor(
        session_factory=get_session,
        payload_cipher=TelegramPayloadCipher(
            settings.telegram_payload_encryption_key,
            settings.telegram_payload_key_version,
        ),
        agent_runner=runner,
        sender=sender,
    )
    assert await processor.run_once() == 1
    assert runner.calls == []
    assert sender.calls == [(333, PAIRING_PENDING_REPLY)]


async def test_auto_approve_pairing_admits_the_next_message_without_operator_review(
    session: AsyncSession,
) -> None:
    code = "auto-approve-code-with-at-least-twenty"
    await _create_pairing_invitation(session, code, auto_approve=True)
    settings = _settings(
        telegram_pairing_enabled=True,
        telegram_pairing_code_pepper="pairing-pepper",
    )
    app = _app(settings)

    pair_response = await _post(
        app,
        _update(601, user_id=1601, text_value=f"/pair {code}"),
    )
    assert pair_response.status_code == 200
    assert pair_response.json()["status"] == "response_ready"

    runner = _Runner()
    sender = _Sender()
    processor = InteractionProcessor(
        session_factory=get_session,
        payload_cipher=TelegramPayloadCipher(
            settings.telegram_payload_encryption_key,
            settings.telegram_payload_key_version,
        ),
        agent_runner=runner,
        sender=sender,
    )
    assert await processor.run_once() == 1
    assert runner.calls == []
    assert sender.calls == [(333, PAIRING_AUTO_APPROVED_REPLY)]

    pairing = TelegramPairingRepository(session)
    assert await pairing.has_active_authorization(1601) is True

    admitted = await _post(app, _update(602, user_id=1601, text_value="hola"))
    assert admitted.json()["status"] == "accepted"


async def test_pairing_is_private_only_and_duplicate_update_has_one_request_and_response(
    session: AsyncSession,
) -> None:
    code = "another-pairing-code-with-at-least-twenty"
    await _create_pairing_invitation(session, code)
    app = _app(
        _settings(
            telegram_pairing_enabled=True,
            telegram_pairing_code_pepper="pairing-pepper",
        )
    )
    group = await _post(
        app,
        _update(511, chat_type="group", user_id=1511, text_value=f"/pair {code}"),
    )
    first = await _post(app, _update(512, user_id=1512, text_value=f"/pair {code}"))
    duplicate = await _post(app, _update(512, user_id=1512, text_value=f"/pair {code}"))

    assert group.json()["status"] == "rejected"
    assert first.json()["status"] == "response_ready"
    assert duplicate.json() == {
        "status": "response_ready",
        "duplicate": True,
        "correlation_id": first.json()["correlation_id"],
    }
    counts = (
        await session.execute(
            text("""
                SELECT
                    (SELECT count(*) FROM ancora.telegram_pairing_requests) AS requests,
                    (SELECT count(*) FROM ancora.logical_responses) AS responses
            """)
        )
    ).one()
    assert (counts.requests, counts.responses) == (1, 1)


async def test_durable_authorization_admits_and_revocation_is_immediate(
    session: AsyncSession,
) -> None:
    code = "authorization-code-with-at-least-twenty"
    await _create_pairing_invitation(session, code)
    pairing = TelegramPairingRepository(session)
    redemption = await pairing.redeem_invitation(
        code_hash=hash_pairing_code(code, "pairing-pepper"),
        telegram_user_id=1601,
    )
    assert redemption.request is not None
    approved = await pairing.approve_request(
        redemption.request.id,
        actor="integration-operator",
        reason="approved evaluator",
    )
    assert approved is not None
    app = _app(
        _settings(
            telegram_pairing_enabled=True,
            telegram_pairing_code_pepper="pairing-pepper",
        )
    )

    authorized = await _post(app, _update(521, user_id=1601, text_value="hola"))
    assert authorized.json()["status"] == "accepted"
    assert await pairing.revoke_authorization(
        1601,
        actor="integration-operator",
        reason="access withdrawn",
    )
    revoked = await _post(app, _update(522, user_id=1601, text_value="hola de nuevo"))

    assert revoked.json()["status"] == "rejected"
    rejected = (
        await session.execute(
            text("SELECT error_detail_code FROM ancora.telegram_interactions WHERE id = :id"),
            {"id": revoked.json()["correlation_id"]},
        )
    ).one()
    assert rejected.error_detail_code == "user_not_allowlisted"
