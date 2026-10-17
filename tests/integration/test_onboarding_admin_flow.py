"""Local dashboard/admin → pairing → admission proofs, without external I/O."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import httpx
import pytest
from cryptography.fernet import Fernet
from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.agent.admin_dashboard import install_admin_dashboard
from src.agent.health import HealthRegistry
from src.agent.telegram_admission import install_telegram_admission_endpoint
from src.agent.telegram_pairing_admin import install_telegram_pairing_admin_api
from src.config import Settings
from src.domain.interactions.pairing import hash_pairing_code
from src.domain.interactions.payloads import TelegramPayloadCipher
from src.domain.interactions.processor import InteractionProcessor
from src.domain.interactions.service import (
    PAIRING_AUTO_APPROVED_REPLY,
    PAIRING_PENDING_REPLY,
    PAIRING_UNAVAILABLE_REPLY,
)
from src.domain.runtime_config.models import bootstrap_runtime_configuration
from src.domain.runtime_config.service import RuntimeConfigManager
from src.repositories.database import get_session
from src.repositories.pairing import TelegramPairingRepository

pytestmark = pytest.mark.integration

DASHBOARD_TOKEN = "local-dashboard-test-token"
CLI_TOKEN = "local-cli-test-token"
ACTOR = "onboarding-test@example.invalid"
REASON = "synthetic local onboarding verification"
USER_ID = 88001


@pytest.fixture
def onboarding_app(session: AsyncSession) -> tuple[FastAPI, Settings]:
    """Install only tested routes; never import main or read a real .env."""
    settings = Settings(
        _env_file=None,
        app_env="development",
        ancora_database_url="postgresql+asyncpg://unused:unused@localhost/unused_test",
        telegram_admission_enabled=True,
        telegram_token="123456:local-test-token",
        telegram_bot_id=88000,
        telegram_webhook_secret_token="local-webhook-test-secret",
        telegram_payload_encryption_key=Fernet.generate_key().decode("ascii"),
        allowed_telegram_user_ids="999",
        telegram_pairing_enabled=True,
        telegram_pairing_admin_enabled=True,
        telegram_pairing_code_pepper="local-test-pepper",
        runtime_config_admin_token=CLI_TOKEN,
        admin_dashboard_enabled=True,
        admin_dashboard_token=DASHBOARD_TOKEN,
    )
    app = FastAPI()
    install_telegram_admission_endpoint(app, settings, get_session)
    install_telegram_pairing_admin_api(app, settings, get_session)
    install_admin_dashboard(
        app,
        settings,
        get_session,
        health_registry=HealthRegistry(),
        runtime_config_manager=RuntimeConfigManager(
            session_factory=get_session, bootstrap=bootstrap_runtime_configuration()
        ),
    )
    return app, settings


def _admin_headers(token: str) -> dict[str, str]:
    return {"authorization": f"Bearer {token}", "x-ancora-admin-actor": ACTOR}


async def _issue(client: httpx.AsyncClient, *, auto_approve: bool = False) -> dict:
    response = await client.post(
        "/admin/dashboard/api/invitations",
        headers=_admin_headers(DASHBOARD_TOKEN),
        json={
            "max_uses": 1,
            "expires_in_minutes": 5,
            "auto_approve": auto_approve,
            "reason": REASON,
        },
    )
    assert response.status_code == 201
    assert response.headers["cache-control"] == "no-store"
    return response.json()


async def _update(client: httpx.AsyncClient, update_id: int, message: str) -> dict:
    response = await client.post(
        "/telegram/webhook",
        headers={"x-telegram-bot-api-secret-token": "local-webhook-test-secret"},
        json={
            "update_id": update_id,
            "message": {
                "message_id": update_id,
                "chat": {"id": USER_ID, "type": "private"},
                "from": {"id": USER_ID},
                "text": message,
            },
        },
    )
    assert response.status_code == 200
    return response.json()


async def _deliver_pairing(settings: Settings, expected: str) -> None:
    runner = AsyncMock()
    runner.run.side_effect = AssertionError("Pairing must never run the Agent")
    sender = AsyncMock()
    sender.send_text.return_value = 88002
    processor = InteractionProcessor(
        session_factory=get_session,
        payload_cipher=TelegramPayloadCipher(
            settings.telegram_payload_encryption_key, settings.telegram_payload_key_version
        ),
        agent_runner=runner,
        sender=sender,
    )
    assert await processor.run_once() == 1
    runner.run.assert_not_awaited()
    sender.send_text.assert_awaited_once_with(USER_ID, expected)


@pytest.mark.parametrize("auto_approve", [False, True], ids=["manual", "auto"])
async def test_dashboard_invitation_admission_and_cli_revocation(
    session: AsyncSession, onboarding_app: tuple[FastAPI, Settings], auto_approve: bool
) -> None:
    app, settings = onboarding_app
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://localhost"
    ) as client:
        blocked = await _update(client, 1, "synthetic request before pairing")
        assert blocked["status"] == "rejected"
        issued = await _issue(client, auto_approve=auto_approve)
        invitation_id = issued["invitation"]["id"]
        code = issued["code"]
        stored = (
            await session.execute(
                text("SELECT code_hash FROM ancora.telegram_pairing_invitations WHERE id=:id"),
                {"id": invitation_id},
            )
        ).scalar_one()
        assert stored == hash_pairing_code(code, settings.telegram_pairing_code_pepper)
        listed = await client.get(
            "/admin/dashboard/api/invitations", headers=_admin_headers(DASHBOARD_TOKEN)
        )
        assert listed.status_code == 200
        assert code not in listed.text
        assert "code_hash" not in listed.text
        assert listed.json()["invitations"][0]["auto_approve"] is auto_approve

        paired = await _update(client, 2, f"/pair {code}")
        assert paired["status"] == "response_ready"
        assert (await _update(client, 2, f"/pair {code}"))["duplicate"] is True
        ciphertext = (
            await session.execute(
                text("SELECT payload_ciphertext FROM ancora.telegram_interactions WHERE id=:id"),
                {"id": paired["correlation_id"]},
            )
        ).scalar_one()
        plaintext = TelegramPayloadCipher(
            settings.telegram_payload_encryption_key, settings.telegram_payload_key_version
        ).decrypt(ciphertext)
        assert code not in str(plaintext)
        await _deliver_pairing(
            settings, PAIRING_AUTO_APPROVED_REPLY if auto_approve else PAIRING_PENDING_REPLY
        )

        pending = await client.get(
            "/admin/telegram-pairing/requests", headers=_admin_headers(CLI_TOKEN)
        )
        assert pending.status_code == 200
        if auto_approve:
            assert pending.json()["requests"] == []
        else:
            blocked = await _update(client, 3, "synthetic request while pending")
            assert blocked["status"] == "rejected"
            request_id = pending.json()["requests"][0]["id"]
            path = f"/admin/telegram-pairing/requests/{request_id}/approve"
            wrong_surface = await client.post(
                path, headers=_admin_headers(DASHBOARD_TOKEN), json={"reason": REASON}
            )
            assert wrong_surface.status_code == 401
            approved = await client.post(
                path, headers=_admin_headers(CLI_TOKEN), json={"reason": REASON}
            )
            assert approved.status_code == 200
            assert approved.json()["decided_by"] == ACTOR
            duplicate = await client.post(
                path, headers=_admin_headers(CLI_TOKEN), json={"reason": REASON}
            )
            assert duplicate.status_code == 409

        admitted = await _update(client, 4, "synthetic request after approval")
        assert admitted["status"] == "accepted"
        revoked = await client.post(
            f"/admin/telegram-pairing/authorizations/{USER_ID}/revoke",
            headers=_admin_headers(CLI_TOKEN),
            json={"reason": "local test closed"},
        )
        assert revoked.status_code == 200
        blocked = await _update(client, 5, "synthetic request after revocation")
        assert blocked["status"] == "rejected"
        assert not await TelegramPairingRepository(session).has_active_authorization(USER_ID)
        audit = (
            await session.execute(
                text("""
                    SELECT authorized_by, revoked_by, revoked_reason, revoked_at
                    FROM ancora.telegram_pairing_authorizations WHERE telegram_user_id=:uid
                """),
                {"uid": USER_ID},
            )
        ).one()
        assert audit.authorized_by == audit.revoked_by == ACTOR
        assert audit.revoked_reason == "local test closed"
        assert audit.revoked_at is not None
        usage = await session.execute(text("SELECT count(*) FROM ancora.llm_usage_events"))
        assert usage.scalar_one() == 0



@pytest.mark.parametrize("state", ["rejected", "revoked", "expired", "exhausted", "invalid"])
async def test_unusable_invitation_never_grants_admission(
    session: AsyncSession, onboarding_app: tuple[FastAPI, Settings], state: str
) -> None:
    app, settings = onboarding_app
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://localhost"
    ) as client:
        issued = await _issue(client)
        invitation_id = issued["invitation"]["id"]
        code = issued["code"]
        repository = TelegramPairingRepository(session)
        if state in {"rejected", "exhausted"}:
            redemption = await repository.redeem_invitation(
                code_hash=hash_pairing_code(code, settings.telegram_pairing_code_pepper),
                telegram_user_id=USER_ID if state == "rejected" else USER_ID + 1,
            )
            assert redemption.request is not None
            if state == "rejected":
                rejected = await client.post(
                    f"/admin/telegram-pairing/requests/{redemption.request.id}/reject",
                    headers=_admin_headers(CLI_TOKEN),
                    json={"reason": REASON},
                )
                assert rejected.status_code == 200
                assert rejected.json()["status"] == "rejected"
        elif state == "revoked":
            revoked = await client.post(
                f"/admin/telegram-pairing/invitations/{invitation_id}/revoke",
                headers=_admin_headers(CLI_TOKEN),
                json={"reason": REASON},
            )
            assert revoked.status_code == 200
            assert revoked.json()["status"] == "revoked"
        elif state == "expired":
            # Local fixture clock only; never change production dates to test TTL.
            await session.execute(
                text("UPDATE ancora.telegram_pairing_invitations SET expires_at=:at WHERE id=:id"),
                {"at": datetime.now(tz=UTC) - timedelta(seconds=1), "id": invitation_id},
            )
            await session.commit()
        else:
            code = "nonexistent-local-test-code-with-sufficient-length"

        assert (await _update(client, 1, f"/pair {code}"))["status"] == "response_ready"
        await _deliver_pairing(settings, PAIRING_UNAVAILABLE_REPLY)
        assert not await repository.has_active_authorization(USER_ID)
        assert (await _update(client, 2, "synthetic denied request"))["status"] == "rejected"
        usage = await session.execute(text("SELECT count(*) FROM ancora.llm_usage_events"))
        assert usage.scalar_one() == 0
