"""Operator web dashboard (BL-43): invitations, runtime config, health, links.

A single HTML page calls the JSON routes below directly from the browser.
Every mutating/listing route is gated by ``ADMIN_DASHBOARD_TOKEN`` — a secret
dedicated to this dashboard, separate from ``RUNTIME_CONFIG_ADMIN_TOKEN`` so a
browser-exposed credential never carries the CLI's runtime-config token. The
underlying domain objects (``TelegramPairingService``, the shared
``RuntimeConfigManager``) are called directly, in process — this module never
re-issues HTTP calls to ``/admin/runtime-config/*`` or
``/admin/telegram-pairing/*``.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Request, status
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from src.agent.health import HealthRegistry
from src.agent.runtime_config_admin import (
    RuntimeConfigActivateRequest,
    RuntimeConfigCreateRevisionRequest,
    RuntimeConfigRollbackRequest,
    RuntimeConfigValidateRequest,
    _actor,
    _authenticate,
    _raise_control_plane_unavailable,
    _reason,
    _revision_response,
    _snapshot_response,
)
from src.agent.telegram_pairing_admin import CreateInvitationRequest
from src.agent.telegram_pairing_admin import _service_factory as _pairing_service_factory
from src.config import Settings
from src.domain.finops.service import (
    FinopsService,
    InvalidWindowError,
    budget_status,
    window_start,
)
from src.domain.interactions.pairing import PairingInvitationCreate
from src.domain.interactions.pairing_service import TelegramPairingService
from src.domain.llm_access.cost_governance import LlmSpendReader
from src.domain.runtime_config.models import RuntimeConfigValidationError
from src.domain.runtime_config.service import (
    RuntimeConfigControlPlaneUnavailableError,
    RuntimeConfigManager,
)
from src.repositories.finops import FinopsRepository
from src.repositories.llm_usage import LlmUsageRepository
from src.repositories.runtime_config import RuntimeConfigConflictError

SessionFactory = Callable[[], Awaitable[AsyncSession]]
PairingServiceFactory = Callable[[AsyncSession], TelegramPairingService]
FinopsServiceFactory = Callable[[AsyncSession], FinopsService]
SpendReaderFactory = Callable[[AsyncSession], LlmSpendReader]

_DASHBOARD_HTML_PATH = Path(__file__).parent / "admin_dashboard_static" / "dashboard.html"


def _configured_links(settings: Settings) -> tuple[tuple[str, str, str | None], ...]:
    """Return (label, url, health_component) for every non-empty operator link."""
    return (
        ("Grafana", settings.admin_link_grafana_url, None),
        ("Railway", settings.admin_link_railway_url, None),
        ("Supabase", settings.admin_link_supabase_url, "database"),
        ("OpenRouter", settings.admin_link_openrouter_url, None),
        ("LiteLLM Gateway", settings.admin_link_litellm_url, "gateway"),
    )


def validate_admin_dashboard_settings(settings: Settings) -> None:
    """Fail closed if the enabled dashboard lacks its DB, token or pepper."""
    if not settings.admin_dashboard_enabled:
        return
    missing = [
        name
        for name, value in (
            ("ANCORA_DATABASE_URL", settings.ancora_database_url),
            ("ADMIN_DASHBOARD_TOKEN", settings.admin_dashboard_token),
            ("TELEGRAM_PAIRING_CODE_PEPPER", settings.telegram_pairing_code_pepper),
        )
        if not value
    ]
    if missing:
        raise ValueError("ADMIN_DASHBOARD_ENABLED requires: " + ", ".join(missing))


def install_admin_dashboard(
    app: FastAPI,
    settings: Settings,
    session_factory: SessionFactory,
    *,
    health_registry: HealthRegistry,
    runtime_config_manager: RuntimeConfigManager,
    pairing_service_factory: PairingServiceFactory | None = None,
    finops_service_factory: FinopsServiceFactory | None = None,
    spend_reader_factory: SpendReaderFactory | None = None,
) -> None:
    """Register the disabled-by-default dashboard page and its JSON API."""
    validate_admin_dashboard_settings(settings)
    if not settings.admin_dashboard_enabled:
        return

    create_service = pairing_service_factory or _pairing_service_factory(settings)
    create_finops = finops_service_factory or (
        lambda session: FinopsService(
            FinopsRepository(session), pseudonym_key=settings.telegram_pairing_code_pepper
        )
    )
    create_spend_reader = spend_reader_factory or LlmUsageRepository
    dashboard_html = _DASHBOARD_HTML_PATH.read_text(encoding="utf-8")

    @app.middleware("http")
    async def _dashboard_security_headers(request: Request, call_next):  # type: ignore[no-untyped-def]
        """Defense-in-depth against token theft via XSS/clickjacking on this page.

        None of this replaces HTTPS: it only narrows what a successful script
        injection on /admin/dashboard* could do with the sessionStorage token
        (no remote script/style loading, no framing, no referrer leakage).
        """
        response = await call_next(request)
        if request.url.path.startswith("/admin/dashboard"):
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; script-src 'self' 'unsafe-inline'; "
                "style-src 'self' 'unsafe-inline'; frame-ancestors 'none'; "
                "base-uri 'none'; form-action 'none'"
            )
            response.headers["X-Frame-Options"] = "DENY"
            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["Referrer-Policy"] = "no-referrer"
            response.headers["Cache-Control"] = "no-store"
        return response

    def _auth(request: Request) -> None:
        _authenticate(request, settings.admin_dashboard_token)

    @app.get("/admin/dashboard", response_class=HTMLResponse)
    async def dashboard_page() -> HTMLResponse:
        return HTMLResponse(dashboard_html)

    @app.get("/admin/dashboard/api/links")
    async def dashboard_links(request: Request) -> dict[str, Any]:
        _auth(request)
        snapshot = health_registry.snapshot()
        components = snapshot.get("components", {})
        assert isinstance(components, dict)
        links: list[dict[str, Any]] = []
        for label, raw_url, health_component in _configured_links(settings):
            url = raw_url.strip()
            if not url:
                continue
            entry: dict[str, Any] = {"name": label, "url": url}
            if health_component is not None and health_component in components:
                entry["health_status"] = components[health_component]["status"]
            links.append(entry)
        return {"links": links}

    def _invalid_window() -> HTTPException:
        return HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="days must be between 1 and 90",
        )

    @app.get("/admin/dashboard/api/finops")
    async def finops_report(request: Request, days: int = 30) -> dict[str, Any]:
        _auth(request)
        now = datetime.now(tz=UTC)
        try:
            since = window_start(now, days)
        except InvalidWindowError:
            raise _invalid_window() from None
        session = await session_factory()
        try:
            governance = runtime_config_manager.snapshot().config.cost_governance
            budget = None
            if governance is not None:
                spend = await create_spend_reader(session).summarize_spend(now=now)
                budget = budget_status(
                    spend.month_usd,
                    spend.today_usd,
                    governance.monthly_budget_usd,
                    governance.daily_budget_usd,
                )
            report = await create_finops(session).finops_report(since, days, budget=budget)
        finally:
            await session.close()
        return report.model_dump(mode="json")

    @app.get("/admin/dashboard/api/quality")
    async def quality_report(request: Request, days: int = 30) -> dict[str, Any]:
        _auth(request)
        try:
            since = window_start(datetime.now(tz=UTC), days)
        except InvalidWindowError:
            raise _invalid_window() from None
        session = await session_factory()
        try:
            report = await create_finops(session).quality_report(since, days)
        finally:
            await session.close()
        return report.model_dump(mode="json")

    @app.get("/admin/dashboard/api/invitations")
    async def list_invitations(request: Request) -> dict[str, Any]:
        _auth(request)
        session = await session_factory()
        try:
            invitations = await create_service(session).list_invitations()
        finally:
            await session.close()
        return {"invitations": [item.model_dump(mode="json") for item in invitations]}

    @app.post(
        "/admin/dashboard/api/invitations",
        status_code=status.HTTP_201_CREATED,
    )
    async def create_invitation(
        request: Request,
        payload: CreateInvitationRequest,
        x_ancora_admin_actor: str | None = Header(default=None),
    ) -> dict[str, Any]:
        _auth(request)
        actor = _actor(x_ancora_admin_actor)
        session = await session_factory()
        try:
            issued = await create_service(session).issue_invitation(
                PairingInvitationCreate.model_validate(payload.model_dump()), actor=actor
            )
        finally:
            await session.close()
        return {"invitation": issued.invitation.model_dump(mode="json"), "code": issued.code}

    @app.get("/admin/dashboard/api/runtime-config/status")
    async def runtime_config_status(request: Request) -> dict[str, Any]:
        _auth(request)
        snapshot = runtime_config_manager.snapshot()
        return {
            "active_revision": snapshot.revision,
            "checksum": snapshot.checksum,
            "source": snapshot.source,
            "default_route": snapshot.config.routing.default_route,
            "database_available": runtime_config_manager.database_available,
            "last_initialize_error": runtime_config_manager.last_initialize_error,
        }

    @app.post("/admin/dashboard/api/runtime-config/validate")
    async def runtime_config_validate(
        request: Request,
        payload: RuntimeConfigValidateRequest,
    ) -> dict[str, Any]:
        _auth(request)
        result = await runtime_config_manager.validate(payload.config)
        return {
            "valid": result.valid,
            "errors": list(result.errors),
            "checksum": result.checksum,
        }

    @app.post(
        "/admin/dashboard/api/runtime-config/revisions",
        status_code=status.HTTP_201_CREATED,
    )
    async def runtime_config_create_revision(
        request: Request,
        payload: RuntimeConfigCreateRevisionRequest,
        x_ancora_admin_actor: str | None = Header(default=None),
    ) -> dict[str, Any]:
        _auth(request)
        actor = _actor(x_ancora_admin_actor)
        reason = _reason(payload.reason)
        try:
            revision = await runtime_config_manager.publish(
                payload.config, actor=actor, reason=reason
            )
        except RuntimeConfigValidationError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail={"errors": list(exc.errors)},
            ) from None
        except RuntimeConfigControlPlaneUnavailableError:
            _raise_control_plane_unavailable()
        return _revision_response(revision)

    @app.post("/admin/dashboard/api/runtime-config/revisions/{revision}/activate")
    async def runtime_config_activate(
        revision: int,
        request: Request,
        payload: RuntimeConfigActivateRequest,
        x_ancora_admin_actor: str | None = Header(default=None),
    ) -> dict[str, Any]:
        _auth(request)
        actor = _actor(x_ancora_admin_actor)
        reason = _reason(payload.reason)
        try:
            snapshot = await runtime_config_manager.activate(
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

    @app.post("/admin/dashboard/api/runtime-config/rollback")
    async def runtime_config_rollback(
        request: Request,
        payload: RuntimeConfigRollbackRequest,
        x_ancora_admin_actor: str | None = Header(default=None),
    ) -> dict[str, Any]:
        _auth(request)
        actor = _actor(x_ancora_admin_actor)
        reason = _reason(payload.reason)
        try:
            snapshot = await runtime_config_manager.rollback(
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
