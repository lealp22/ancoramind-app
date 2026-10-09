"""Protected HTTPS control-plane API for the manual emergency stop (BL-44/specs/031).

Reuses the runtime-config admin gate (``RUNTIME_CONFIG_ADMIN_ENABLED`` +
``RUNTIME_CONFIG_ADMIN_TOKEN``) instead of a new secret: this is the same
protected control-plane surface, just a different manager.
"""

from __future__ import annotations

import hmac
import logging
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field

from src.config import Settings
from src.domain.emergency_stop.models import EmergencyStopState
from src.domain.emergency_stop.service import EmergencyStopManager

logger = logging.getLogger(__name__)


class EmergencyStopAdminModel(BaseModel):
    """Reject unknown HTTP control-plane fields before they reach the manager."""

    model_config = ConfigDict(extra="forbid")


class EmergencyStopActivateRequest(EmergencyStopAdminModel):
    reason: str = Field(min_length=1, max_length=2000)


class EmergencyStopDeactivateRequest(EmergencyStopAdminModel):
    reason: str = Field(min_length=1, max_length=2000)


def install_emergency_stop_admin_api(
    app: FastAPI,
    settings: Settings,
    manager: EmergencyStopManager,
) -> None:
    """Register disabled-by-default admin endpoints; never expose them as Agent tools."""
    if not settings.runtime_config_admin_enabled:
        return

    @app.get("/admin/emergency-stop/status")
    async def emergency_stop_status(request: Request) -> dict[str, Any]:
        _authenticate(request, settings.runtime_config_admin_token)
        return _state_response(manager.current())

    @app.post("/admin/emergency-stop/activate")
    async def activate_emergency_stop(
        request: Request,
        payload: EmergencyStopActivateRequest,
        x_ancora_admin_actor: str | None = Header(default=None),
    ) -> dict[str, Any]:
        _authenticate(request, settings.runtime_config_admin_token)
        actor = _actor(x_ancora_admin_actor)
        reason = _reason(payload.reason)
        try:
            state = manager.activate(actor=actor, reason=reason)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=str(exc),
            ) from None
        return _state_response(state)

    @app.post("/admin/emergency-stop/deactivate")
    async def deactivate_emergency_stop(
        request: Request,
        payload: EmergencyStopDeactivateRequest,
        x_ancora_admin_actor: str | None = Header(default=None),
    ) -> dict[str, Any]:
        _authenticate(request, settings.runtime_config_admin_token)
        actor = _actor(x_ancora_admin_actor)
        reason = _reason(payload.reason)
        try:
            state = manager.deactivate(actor=actor, reason=reason)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=str(exc),
            ) from None
        return _state_response(state)


def _authenticate(request: Request, expected_token: str) -> None:
    authorization = request.headers.get("authorization", "")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token or not hmac.compare_digest(token, expected_token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid runtime config admin credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )


def _actor(value: str | None) -> str:
    actor = (value or "").strip()
    if not actor:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="X-Ancora-Admin-Actor header is required",
        )
    return actor


def _reason(value: str) -> str:
    reason = value.strip()
    if not reason:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="reason must not be blank",
        )
    return reason


def _state_response(state: EmergencyStopState) -> dict[str, Any]:
    return {
        "active": state.active,
        "reason": state.reason,
        "activated_by": state.activated_by,
        "activated_at": state.activated_at,
    }


__all__ = ["install_emergency_stop_admin_api"]
