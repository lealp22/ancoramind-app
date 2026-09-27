"""Unit tests for the first governed Telegram pairing increment (BL-24)."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession

from src.agent.telegram_pairing_admin import (
    install_telegram_pairing_admin_api,
    validate_telegram_pairing_admin_settings,
)
from src.config import Settings
from src.domain.interactions.pairing import (
    IssuedPairingInvitation,
    PairingInvitation,
    PairingInvitationCreate,
    PairingInvitationStatus,
    PairingRequest,
    PairingRequestStatus,
    hash_pairing_code,
)
from src.domain.interactions.pairing_service import TelegramPairingService
from src.repositories.pairing import TelegramPairingRepository


def _settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "ancora_database_url": "postgresql+asyncpg://user:pass@localhost/db",
        "runtime_config_admin_token": "admin-secret",
        "telegram_pairing_admin_enabled": True,
        "telegram_pairing_code_pepper": "pairing-pepper",
    }
    values.update(overrides)
    return Settings(**values)


def _invitation() -> PairingInvitation:
    return PairingInvitation(
        id=uuid4(),
        status=PairingInvitationStatus.ACTIVE,
        max_uses=1,
        use_count=0,
        expires_at=datetime(2026, 9, 27, 12, tzinfo=UTC),
        created_by="operator",
        reason="controlled evaluator",
        created_at=datetime(2026, 9, 27, 11, tzinfo=UTC),
    )


async def _post(
    app: FastAPI,
    path: str,
    body: dict[str, object],
    *,
    token: str | None = "admin-secret",
    actor: str | None = "operator",
) -> httpx.Response:
    headers: dict[str, str] = {}
    if token is not None:
        headers["authorization"] = f"Bearer {token}"
    if actor is not None:
        headers["x-ancora-admin-actor"] = actor
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.post(path, json=body, headers=headers)


@pytest.mark.parametrize(
    ("override", "expected_name"),
    [
        ({"ancora_database_url": ""}, "ANCORA_DATABASE_URL"),
        ({"runtime_config_admin_token": ""}, "RUNTIME_CONFIG_ADMIN_TOKEN"),
        ({"telegram_pairing_code_pepper": ""}, "TELEGRAM_PAIRING_CODE_PEPPER"),
    ],
)
def test_pairing_admin_requires_every_security_prerequisite(
    override: dict[str, object], expected_name: str
) -> None:
    with pytest.raises(ValueError, match=expected_name):
        validate_telegram_pairing_admin_settings(_settings(**override))


def test_pairing_code_hash_is_keyed_and_never_the_raw_code() -> None:
    raw_code = "a-private-invitation-code"

    assert hash_pairing_code(raw_code, "pepper-a") != hash_pairing_code(raw_code, "pepper-b")
    assert raw_code not in hash_pairing_code(raw_code, "pepper-a")


async def test_issue_invitation_persists_only_the_keyed_hash() -> None:
    repository = AsyncMock(spec=TelegramPairingRepository)
    repository.create_invitation.return_value = _invitation()
    service = TelegramPairingService(repository, code_pepper="pairing-pepper")

    issued = await service.issue_invitation(
        PairingInvitationCreate(reason="controlled evaluator"), actor="operator"
    )

    assert issued.code
    assert repository.create_invitation.await_args.kwargs["code_hash"] == hash_pairing_code(
        issued.code, "pairing-pepper"
    )
    assert issued.code not in repository.create_invitation.await_args.kwargs["code_hash"]


async def test_admin_issue_returns_code_once_and_requires_bearer_and_actor() -> None:
    app = FastAPI()
    session = AsyncMock(spec=AsyncSession)
    session_factory = AsyncMock(return_value=session)
    service = AsyncMock()
    service.issue_invitation.return_value = IssuedPairingInvitation(
        invitation=_invitation(), code="one-time-code-with-sufficient-length"
    )
    install_telegram_pairing_admin_api(
        app, _settings(), session_factory, service_factory=lambda _: service
    )

    path = "/admin/telegram-pairing/invitations"
    body = {"reason": "controlled evaluator"}
    assert (await _post(app, path, body, token=None)).status_code == 401
    assert (await _post(app, path, body, actor=None)).status_code == 422

    response = await _post(app, path, body)

    assert response.status_code == 201
    assert response.json()["code"] == "one-time-code-with-sufficient-length"
    assert response.json()["invitation"]["status"] == "active"
    assert "code_hash" not in response.json()["invitation"]
    assert service.issue_invitation.await_args.kwargs["actor"] == "operator"
    session.close.assert_awaited_once()


async def test_admin_approval_and_revocation_use_protected_operator_api() -> None:
    app = FastAPI()
    session = AsyncMock(spec=AsyncSession)
    session_factory = AsyncMock(return_value=session)
    service = AsyncMock()
    request = PairingRequest(
        id=uuid4(),
        invitation_id=uuid4(),
        telegram_user_id=42,
        status=PairingRequestStatus.APPROVED,
        requested_at=datetime(2026, 9, 27, 11, tzinfo=UTC),
        decided_by="operator",
        decision_reason="verified",
        decided_at=datetime(2026, 9, 27, 11, 1, tzinfo=UTC),
    )
    service.approve_request.return_value = request
    service.revoke_invitation.return_value = _invitation().model_copy(
        update={"status": PairingInvitationStatus.REVOKED}
    )
    service.revoke_authorization.return_value = True
    install_telegram_pairing_admin_api(
        app, _settings(), session_factory, service_factory=lambda _: service
    )

    approved = await _post(
        app,
        f"/admin/telegram-pairing/requests/{request.id}/approve",
        {"reason": "verified"},
    )
    revoked = await _post(
        app,
        f"/admin/telegram-pairing/invitations/{uuid4()}/revoke",
        {"reason": "no longer distributing this invitation"},
    )
    authorization_revoked = await _post(
        app,
        "/admin/telegram-pairing/authorizations/42/revoke",
        {"reason": "no longer participating"},
    )

    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"
    assert revoked.status_code == 200
    assert revoked.json()["status"] == "revoked"
    assert authorization_revoked.status_code == 200
    assert authorization_revoked.json() == {"revoked": True}
