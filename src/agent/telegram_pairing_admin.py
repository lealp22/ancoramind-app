"""Protected operator API for governed Telegram pairing invitations (BL-24)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Query, Request, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.agent.runtime_config_admin import _actor, _authenticate, _reason
from src.config import Settings
from src.domain.interactions.pairing import PairingInvitationCreate
from src.domain.interactions.pairing_service import TelegramPairingService
from src.repositories.pairing import TelegramPairingRepository

SessionFactory = Callable[[], Awaitable[AsyncSession]]
ServiceFactory = Callable[[AsyncSession], TelegramPairingService]


class PairingAdminModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CreateInvitationRequest(PairingAdminModel):
    max_uses: int = Field(default=1, ge=1, le=100)
    expires_in_minutes: int = Field(default=60, ge=5, le=43200)
    """Up to 30 days. A long-lived code enlarges the leak window if the raw
    code is captured before redemption; prefer a low max_uses alongside a
    long expiry."""
    reason: str = Field(min_length=1, max_length=2000)


class DecisionRequest(PairingAdminModel):
    reason: str = Field(min_length=1, max_length=2000)


def validate_telegram_pairing_admin_settings(settings: Settings) -> None:
    if not settings.telegram_pairing_admin_enabled:
        return
    missing = [
        name
        for name, value in (
            ("ANCORA_DATABASE_URL", settings.ancora_database_url),
            ("RUNTIME_CONFIG_ADMIN_TOKEN", settings.runtime_config_admin_token),
            ("TELEGRAM_PAIRING_CODE_PEPPER", settings.telegram_pairing_code_pepper),
        )
        if not value
    ]
    if missing:
        raise ValueError("TELEGRAM_PAIRING_ADMIN_ENABLED requires: " + ", ".join(missing))


def install_telegram_pairing_admin_api(
    app: FastAPI,
    settings: Settings,
    session_factory: SessionFactory,
    service_factory: ServiceFactory | None = None,
) -> None:
    """Install disabled-by-default admin endpoints; codes are returned only once."""
    validate_telegram_pairing_admin_settings(settings)
    if not settings.telegram_pairing_admin_enabled:
        return

    create_service = service_factory or _service_factory(settings)

    @app.post("/admin/telegram-pairing/invitations", status_code=status.HTTP_201_CREATED)
    async def create_invitation(
        request: Request,
        payload: CreateInvitationRequest,
        x_ancora_admin_actor: str | None = Header(default=None),
    ) -> dict[str, Any]:
        _authenticate(request, settings.runtime_config_admin_token)
        actor = _actor(x_ancora_admin_actor)
        session = await session_factory()
        try:
            issued = await create_service(session).issue_invitation(
                PairingInvitationCreate.model_validate(payload.model_dump()), actor=actor
            )
        finally:
            await session.close()
        return {"invitation": issued.invitation.model_dump(mode="json"), "code": issued.code}

    @app.post("/admin/telegram-pairing/requests/{request_id}/approve")
    async def approve_request(
        request: Request,
        request_id: str,
        payload: DecisionRequest,
        x_ancora_admin_actor: str | None = Header(default=None),
    ) -> dict[str, Any]:
        _authenticate(request, settings.runtime_config_admin_token)
        actor = _actor(x_ancora_admin_actor)
        try:
            session = await session_factory()
            try:
                approved = await create_service(session).approve_request(
                    request_id, actor=actor, reason=_reason(payload.reason)
                )
            finally:
                await session.close()
        except ValueError:
            raise HTTPException(status_code=422, detail="Invalid pairing request ID") from None
        if approved is None:
            raise HTTPException(status_code=409, detail="Pairing request is not pending")
        return approved.model_dump(mode="json")

    @app.get("/admin/telegram-pairing/requests")
    async def list_pending_requests(
        request: Request,
        limit: int = Query(default=100, ge=1, le=100),
    ) -> dict[str, Any]:
        _authenticate(request, settings.runtime_config_admin_token)
        session = await session_factory()
        try:
            pending = await create_service(session).list_pending_requests(limit)
        finally:
            await session.close()
        return {"requests": [item.model_dump(mode="json") for item in pending]}

    @app.post("/admin/telegram-pairing/requests/{request_id}/reject")
    async def reject_request(
        request: Request,
        request_id: str,
        payload: DecisionRequest,
        x_ancora_admin_actor: str | None = Header(default=None),
    ) -> dict[str, Any]:
        _authenticate(request, settings.runtime_config_admin_token)
        actor = _actor(x_ancora_admin_actor)
        try:
            session = await session_factory()
            try:
                rejected = await create_service(session).reject_request(
                    request_id, actor=actor, reason=_reason(payload.reason)
                )
            finally:
                await session.close()
        except ValueError:
            raise HTTPException(status_code=422, detail="Invalid pairing request ID") from None
        if rejected is None:
            raise HTTPException(status_code=409, detail="Pairing request is not pending")
        return rejected.model_dump(mode="json")

    @app.post("/admin/telegram-pairing/invitations/{invitation_id}/revoke")
    async def revoke_invitation(
        request: Request,
        invitation_id: str,
        payload: DecisionRequest,
        x_ancora_admin_actor: str | None = Header(default=None),
    ) -> dict[str, Any]:
        _authenticate(request, settings.runtime_config_admin_token)
        actor = _actor(x_ancora_admin_actor)
        try:
            session = await session_factory()
            try:
                invitation = await create_service(session).revoke_invitation(
                    invitation_id, actor=actor, reason=_reason(payload.reason)
                )
            finally:
                await session.close()
        except ValueError:
            raise HTTPException(status_code=422, detail="Invalid pairing invitation ID") from None
        if invitation is None:
            raise HTTPException(status_code=409, detail="Pairing invitation is not active")
        return invitation.model_dump(mode="json")

    @app.post("/admin/telegram-pairing/authorizations/{telegram_user_id}/revoke")
    async def revoke_authorization(
        request: Request,
        telegram_user_id: int,
        payload: DecisionRequest,
        x_ancora_admin_actor: str | None = Header(default=None),
    ) -> dict[str, bool]:
        _authenticate(request, settings.runtime_config_admin_token)
        actor = _actor(x_ancora_admin_actor)
        session = await session_factory()
        try:
            revoked = await create_service(session).revoke_authorization(
                telegram_user_id, actor=actor, reason=_reason(payload.reason)
            )
        finally:
            await session.close()
        if not revoked:
            raise HTTPException(status_code=404, detail="Active pairing authorization not found")
        return {"revoked": True}


def _service_factory(settings: Settings) -> ServiceFactory:
    def create(session: AsyncSession) -> TelegramPairingService:
        return TelegramPairingService(
            TelegramPairingRepository(session), code_pepper=settings.telegram_pairing_code_pepper
        )

    return create
