"""AncoraMind-owned Telegram admission endpoint for specs/013 T4.

This adapter owns deterministic HTTP admission only. It deliberately does not
invoke Agno, start an Agent run, or process an interaction; those responsibilities
belong to T5 after a durable ``accepted`` claim exists in PostgreSQL.
"""

from __future__ import annotations

import hmac
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import FastAPI, HTTPException, Request, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import Settings
from src.domain.interactions.admission import TelegramAdmissionPolicy
from src.domain.interactions.models import TelegramAdmissionLimits
from src.domain.interactions.payloads import TelegramPayloadCipher
from src.domain.interactions.service import TelegramInteractionService
from src.repositories.interactions import TelegramInteractionsRepository

logger = logging.getLogger(__name__)

SessionFactory = Callable[[], Awaitable[AsyncSession]]
ServiceFactory = Callable[[AsyncSession], TelegramInteractionService]


def validate_telegram_admission_settings(settings: Settings) -> None:
    """Fail closed when the enabled durable endpoint lacks a security prerequisite."""
    if not settings.telegram_admission_enabled:
        return

    missing: list[str] = []
    if not settings.ancora_database_url:
        missing.append("ANCORA_DATABASE_URL")
    if not settings.telegram_bot_id:
        missing.append("TELEGRAM_BOT_ID")
    if not settings.telegram_webhook_secret_token:
        missing.append("TELEGRAM_WEBHOOK_SECRET_TOKEN")
    if not settings.telegram_payload_encryption_key:
        missing.append("TELEGRAM_PAYLOAD_ENCRYPTION_KEY")
    if not settings.allowed_user_ids:
        missing.append("ALLOWED_TELEGRAM_USER_IDS")
    if missing:
        raise ValueError("TELEGRAM_ADMISSION_ENABLED requires: " + ", ".join(missing))


def install_telegram_admission_endpoint(
    app: FastAPI,
    settings: Settings,
    session_factory: SessionFactory,
    service_factory: ServiceFactory | None = None,
) -> None:
    """Register the durable Telegram admission handler at the stable webhook URL."""
    validate_telegram_admission_settings(settings)
    if not settings.telegram_admission_enabled:
        return

    make_service = service_factory or _service_factory(settings)

    @app.post("/telegram/webhook", status_code=status.HTTP_200_OK)
    async def telegram_webhook(request: Request) -> dict[str, Any]:
        _validate_secret(request, settings.telegram_webhook_secret_token)
        update = await _parse_update(request)

        session: AsyncSession | None = None
        try:
            session = await session_factory()
            result = await make_service(session).admit_update(
                bot_id=settings.telegram_bot_id,
                update=update,
                railway_request_id=request.headers.get("x-railway-request-id"),
                limits=_admission_limits(settings),
                policy=TelegramAdmissionPolicy(set(settings.allowed_user_ids)),
            )
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Malformed Telegram update",
            ) from None
        except (SQLAlchemyError, RuntimeError):
            # Do not include the exception: it could contain SQL details or request data.
            logger.warning("Telegram admission could not persist the interaction")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Telegram admission temporarily unavailable",
            ) from None
        finally:
            if session is not None:
                await session.close()

        return {
            "status": result.interaction.status.value,
            "duplicate": result.duplicate,
            "correlation_id": str(result.interaction.correlation_id),
        }


def _service_factory(settings: Settings) -> ServiceFactory:
    """Build stateless service dependencies once from startup-only secrets/config."""
    cipher = TelegramPayloadCipher(
        settings.telegram_payload_encryption_key,
        settings.telegram_payload_key_version,
    )

    def create(session: AsyncSession) -> TelegramInteractionService:
        return TelegramInteractionService(TelegramInteractionsRepository(session), cipher)

    return create


def _admission_limits(settings: Settings) -> TelegramAdmissionLimits:
    return TelegramAdmissionLimits(
        user_burst=settings.telegram_admission_user_burst,
        burst_window_seconds=settings.telegram_admission_burst_window_seconds,
        user_requests_per_minute=settings.telegram_admission_user_requests_per_minute,
        user_requests_per_hour=settings.telegram_admission_user_requests_per_hour,
        pending_global=settings.telegram_admission_pending_global,
        queued_per_chat=settings.telegram_admission_queued_per_chat,
    )


def _validate_secret(request: Request, expected_secret: str) -> None:
    received_secret = request.headers.get("x-telegram-bot-api-secret-token")
    if received_secret is None or not hmac.compare_digest(received_secret, expected_secret):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid Telegram webhook secret",
        )


async def _parse_update(request: Request) -> dict[str, Any]:
    try:
        payload = await request.json()
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Malformed Telegram update",
        ) from None
    if not isinstance(payload, dict):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Telegram update must be an object",
        )
    if not isinstance(payload.get("update_id"), int):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Malformed Telegram update",
        )
    return payload
