"""Unit tests for the deterministic Telegram admission HTTP adapter (T4)."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import httpx
import pytest
from cryptography.fernet import Fernet
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession

from src.agent.telegram_admission import (
    install_telegram_admission_endpoint,
    validate_telegram_admission_settings,
)
from src.config import Settings
from src.domain.interactions.models import (
    InteractionStatus,
    TelegramAdmissionResult,
    TelegramInteraction,
)


def _settings(**overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "telegram_admission_enabled": True,
        "telegram_token": "123456:token",
        "ancora_database_url": "postgresql+asyncpg://user:pass@localhost/db",
        "telegram_bot_id": 456,
        "telegram_webhook_secret_token": "webhook-secret",
        "telegram_payload_encryption_key": Fernet.generate_key().decode("ascii"),
        "allowed_telegram_user_ids": "999",
    }
    values.update(overrides)
    return Settings(**values)


def _update(
    update_id: int = 1, *, chat_type: str = "private", user_id: int = 999
) -> dict[str, Any]:
    return {
        "update_id": update_id,
        "message": {
            "message_id": 2,
            "chat": {"id": 3, "type": chat_type},
            "from": {"id": user_id},
            "text": "private content",
        },
    }


async def _post(app: FastAPI, payload: object, *, secret: str = "webhook-secret") -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.post(
            "/telegram/webhook",
            json=payload,
            headers={"x-telegram-bot-api-secret-token": secret},
        )


@pytest.mark.parametrize(
    ("override", "expected_name"),
    [
        ({"ancora_database_url": ""}, "ANCORA_DATABASE_URL"),
        ({"telegram_bot_id": 0}, "TELEGRAM_BOT_ID"),
        ({"telegram_webhook_secret_token": ""}, "TELEGRAM_WEBHOOK_SECRET_TOKEN"),
        ({"telegram_payload_encryption_key": ""}, "TELEGRAM_PAYLOAD_ENCRYPTION_KEY"),
        ({"allowed_telegram_user_ids": ""}, "ALLOWED_TELEGRAM_USER_IDS"),
    ],
)
def test_enabled_admission_requires_every_security_prerequisite(
    override: dict[str, object], expected_name: str
) -> None:
    with pytest.raises(ValueError, match=expected_name):
        validate_telegram_admission_settings(_settings(**override))


async def test_invalid_secret_is_rejected_without_opening_session() -> None:
    app = FastAPI()
    session_factory = AsyncMock()
    install_telegram_admission_endpoint(app, _settings(), session_factory)

    response = await _post(app, _update(), secret="wrong-secret")

    assert response.status_code == 403
    session_factory.assert_not_awaited()


async def test_malformed_update_returns_400_without_opening_session() -> None:
    app = FastAPI()
    session_factory = AsyncMock()
    install_telegram_admission_endpoint(app, _settings(), session_factory)

    response = await _post(app, {"update_id": "not-an-integer"})

    assert response.status_code == 400
    session_factory.assert_not_awaited()


async def test_database_unavailable_returns_503() -> None:
    app = FastAPI()
    session_factory = AsyncMock(side_effect=RuntimeError("database unavailable"))
    install_telegram_admission_endpoint(app, _settings(), session_factory)

    response = await _post(app, _update())

    assert response.status_code == 503


async def test_endpoint_returns_minimal_admission_metadata() -> None:
    app = FastAPI()
    mock_session = AsyncMock(spec=AsyncSession)
    session_factory = AsyncMock(return_value=mock_session)
    service = AsyncMock()
    interaction = TelegramInteraction.model_validate(
        {
            "id": "0c9ce867-76d7-4247-aa1f-85d9f28d9e3d",
            "bot_id": 456,
            "telegram_update_id": 1,
            "telegram_message_id": 2,
            "chat_id": 3,
            "telegram_user_id": 999,
            "update_type": "message",
            "status": "accepted",
            "received_at": "2026-09-13T00:00:00Z",
            "accepted_at": "2026-09-13T00:00:00Z",
            "updated_at": "2026-09-13T00:00:00Z",
        }
    )
    service.admit_update.return_value = TelegramAdmissionResult(
        interaction=interaction,
        duplicate=False,
    )
    install_telegram_admission_endpoint(
        app,
        _settings(),
        session_factory,
        service_factory=lambda _: service,
    )

    response = await _post(app, _update())

    assert response.status_code == 200
    assert response.json() == {
        "status": InteractionStatus.ACCEPTED,
        "duplicate": False,
        "correlation_id": "0c9ce867-76d7-4247-aa1f-85d9f28d9e3d",
    }
    assert "private content" not in response.text
    mock_session.close.assert_awaited_once()
