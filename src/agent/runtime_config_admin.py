"""Protected HTTPS control-plane API for specs/013 runtime configuration."""

from __future__ import annotations

import hmac
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import Settings
from src.domain.runtime_config.models import RuntimeConfigValidationError
from src.domain.runtime_config.service import (
    RuntimeConfigControlPlaneUnavailableError,
    RuntimeConfigManager,
)
from src.repositories.runtime_config import RuntimeConfigConflictError

logger = logging.getLogger(__name__)

SessionFactory = Callable[[], Awaitable[AsyncSession]]


class RuntimeConfigAdminModel(BaseModel):
    """Reject unknown HTTP control-plane fields before they reach the manager."""

    model_config = ConfigDict(extra="forbid")


class RuntimeConfigValidateRequest(RuntimeConfigAdminModel):
    config: dict[str, Any]


class RuntimeConfigCreateRevisionRequest(RuntimeConfigAdminModel):
    config: dict[str, Any]
    reason: str = Field(min_length=1, max_length=2000)


class RuntimeConfigActivateRequest(RuntimeConfigAdminModel):
    expected_current_revision: int = Field(ge=1)
    reason: str = Field(min_length=1, max_length=2000)


class RuntimeConfigRollbackRequest(RuntimeConfigAdminModel):
    revision: int = Field(ge=1)
    expected_current_revision: int = Field(ge=1)
    reason: str = Field(min_length=1, max_length=2000)


def validate_runtime_config_admin_settings(settings: Settings) -> None:
    """Fail closed if the enabled admin control plane lacks its DB or bearer secret."""
    if not settings.runtime_config_admin_enabled:
        return
    missing: list[str] = []
    if not settings.ancora_database_url:
        missing.append("ANCORA_DATABASE_URL")
    if not settings.runtime_config_admin_token:
        missing.append("RUNTIME_CONFIG_ADMIN_TOKEN")
    if missing:
        raise ValueError("RUNTIME_CONFIG_ADMIN_ENABLED requires: " + ", ".join(missing))


def create_runtime_config_manager(
    settings: Settings,
    session_factory: SessionFactory,
) -> RuntimeConfigManager:
    """Construct the cached manager from a secret-free environment bootstrap."""
    from src.domain.runtime_config.models import bootstrap_runtime_configuration

    return RuntimeConfigManager(
        session_factory=session_factory,
        bootstrap=bootstrap_runtime_configuration(settings.runtime_config_bootstrap_default_route),
    )


def install_runtime_config_admin_api(
    app: FastAPI,
    settings: Settings,
    manager: RuntimeConfigManager,
) -> None:
    """Register disabled-by-default admin endpoints; never expose them as Agent tools."""
    validate_runtime_config_admin_settings(settings)
    if not settings.runtime_config_admin_enabled:
        return

    @app.get("/admin/runtime-config/status")
    async def runtime_config_status(request: Request) -> dict[str, Any]:
        _authenticate(request, settings.runtime_config_admin_token)
        snapshot = manager.snapshot()
        return {
            "active_revision": snapshot.revision,
            "checksum": snapshot.checksum,
            "source": snapshot.source,
            "default_route": snapshot.config.routing.default_route,
            "database_available": manager.database_available,
            "last_initialize_error": manager.last_initialize_error,
        }

    @app.post("/admin/runtime-config/validate")
    async def validate_runtime_config(
        request: Request,
        payload: RuntimeConfigValidateRequest,
    ) -> dict[str, Any]:
        _authenticate(request, settings.runtime_config_admin_token)
        result = await manager.validate(payload.config)
        return {
            "valid": result.valid,
            "errors": list(result.errors),
            "checksum": result.checksum,
        }

    @app.post("/admin/runtime-config/revisions", status_code=status.HTTP_201_CREATED)
    async def create_runtime_config_revision(
        request: Request,
        payload: RuntimeConfigCreateRevisionRequest,
        x_ancora_admin_actor: str | None = Header(default=None),
    ) -> dict[str, Any]:
        _authenticate(request, settings.runtime_config_admin_token)
        actor = _actor(x_ancora_admin_actor)
        reason = _reason(payload.reason)
        try:
            revision = await manager.publish(payload.config, actor=actor, reason=reason)
        except RuntimeConfigValidationError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail={"errors": list(exc.errors)},
            ) from None
        except RuntimeConfigControlPlaneUnavailableError:
            _raise_control_plane_unavailable()
        return _revision_response(revision)

    @app.post("/admin/runtime-config/revisions/{revision}/activate")
    async def activate_runtime_config_revision(
        revision: int,
        request: Request,
        payload: RuntimeConfigActivateRequest,
        x_ancora_admin_actor: str | None = Header(default=None),
    ) -> dict[str, Any]:
        _authenticate(request, settings.runtime_config_admin_token)
        actor = _actor(x_ancora_admin_actor)
        reason = _reason(payload.reason)
        try:
            snapshot = await manager.activate(
                revision,
                expected_current_revision=payload.expected_current_revision,
                actor=actor,
                reason=reason,
            )
        except KeyError:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Revision not found",
            ) from None
        except RuntimeConfigConflictError:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Active revision changed; refresh status and retry explicitly",
            ) from None
        except RuntimeConfigValidationError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail={"errors": list(exc.errors)},
            ) from None
        except RuntimeConfigControlPlaneUnavailableError:
            _raise_control_plane_unavailable()
        return _snapshot_response(snapshot)

    @app.post("/admin/runtime-config/rollback")
    async def rollback_runtime_config(
        request: Request,
        payload: RuntimeConfigRollbackRequest,
        x_ancora_admin_actor: str | None = Header(default=None),
    ) -> dict[str, Any]:
        _authenticate(request, settings.runtime_config_admin_token)
        actor = _actor(x_ancora_admin_actor)
        reason = _reason(payload.reason)
        try:
            snapshot = await manager.rollback(
                payload.revision,
                expected_current_revision=payload.expected_current_revision,
                actor=actor,
                reason=reason,
            )
        except KeyError:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Revision not found",
            ) from None
        except RuntimeConfigConflictError:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Active revision changed; refresh status and retry explicitly",
            ) from None
        except RuntimeConfigValidationError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail={"errors": list(exc.errors)},
            ) from None
        except RuntimeConfigControlPlaneUnavailableError:
            _raise_control_plane_unavailable()
        return _snapshot_response(snapshot)


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


def _raise_control_plane_unavailable() -> None:
    logger.warning("Runtime config control-plane database is unavailable")
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Runtime config control plane temporarily unavailable",
    )


def _revision_response(revision: Any) -> dict[str, Any]:
    return {
        "revision": revision.revision,
        "checksum": revision.checksum,
        "validation_status": revision.validation_status,
        "created_by": revision.created_by,
        "reason": revision.reason,
        "created_at": revision.created_at,
    }


def _snapshot_response(snapshot: Any) -> dict[str, Any]:
    return {
        "active_revision": snapshot.revision,
        "checksum": snapshot.checksum,
        "source": snapshot.source,
        "default_route": snapshot.config.routing.default_route,
    }
