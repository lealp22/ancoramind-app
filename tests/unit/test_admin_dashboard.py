"""Unit tests for the operator admin dashboard (BL-43): auth gates and wiring.

The dashboard calls domain logic (TelegramPairingService, RuntimeConfigManager)
directly rather than re-issuing HTTP calls to the existing /admin/* admin
APIs, so these tests focus on: settings fail-closed behavior, the dashboard
page being served/withheld, and that every JSON route is gated by
ADMIN_DASHBOARD_TOKEN (never RUNTIME_CONFIG_ADMIN_TOKEN) and wired to the
right domain call.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI

from src.agent.admin_dashboard import (
    install_admin_dashboard,
    validate_admin_dashboard_settings,
)
from src.agent.health import HealthRegistry
from src.config import Settings
from src.domain.interactions.pairing import (
    IssuedPairingInvitation,
    PairingInvitation,
    PairingInvitationStatus,
)
from src.domain.runtime_config.models import bootstrap_runtime_configuration
from src.domain.runtime_config.service import RuntimeConfigManager


def _settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "ancora_database_url": "postgresql+asyncpg://user:pass@localhost/db",
        "admin_dashboard_enabled": True,
        "admin_dashboard_token": "dashboard-secret",
        "telegram_pairing_code_pepper": "pairing-pepper",
    }
    values.update(overrides)
    return Settings(**values)


def _manager() -> RuntimeConfigManager:
    return RuntimeConfigManager(
        session_factory=AsyncMock(), bootstrap=bootstrap_runtime_configuration()
    )


def _invitation() -> PairingInvitation:
    return PairingInvitation(
        id=uuid4(),
        status=PairingInvitationStatus.ACTIVE,
        max_uses=1,
        use_count=0,
        expires_at=datetime(2026, 10, 5, 12, tzinfo=UTC),
        created_by="operator",
        reason="evaluator",
        created_at=datetime(2026, 10, 5, 11, tzinfo=UTC),
    )


def _install(
    settings: Settings,
    *,
    pairing_service: object | None = None,
    manager: RuntimeConfigManager | None = None,
    health_registry: HealthRegistry | None = None,
) -> FastAPI:
    app = FastAPI()
    install_admin_dashboard(
        app,
        settings,
        AsyncMock(return_value=AsyncMock()),
        health_registry=health_registry or HealthRegistry(),
        runtime_config_manager=manager or _manager(),
        pairing_service_factory=(lambda _: pairing_service) if pairing_service else None,
    )
    return app


async def _get(
    app: FastAPI, path: str, *, token: str | None = "dashboard-secret"
) -> httpx.Response:
    headers = {"authorization": f"Bearer {token}"} if token is not None else {}
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.get(path, headers=headers)


async def _post(
    app: FastAPI,
    path: str,
    body: dict[str, object],
    *,
    token: str | None = "dashboard-secret",
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
        ({"admin_dashboard_token": ""}, "ADMIN_DASHBOARD_TOKEN"),
        ({"telegram_pairing_code_pepper": ""}, "TELEGRAM_PAIRING_CODE_PEPPER"),
    ],
)
def test_dashboard_requires_every_security_prerequisite(
    override: dict[str, object], expected_name: str
) -> None:
    with pytest.raises(ValueError, match=expected_name):
        validate_admin_dashboard_settings(_settings(**override))


async def test_dashboard_routes_absent_when_disabled() -> None:
    app = _install(_settings(admin_dashboard_enabled=False))

    assert (await _get(app, "/admin/dashboard", token=None)).status_code == 404
    assert (await _get(app, "/admin/dashboard/api/links")).status_code == 404


async def test_dashboard_page_is_served_without_a_token() -> None:
    app = _install(_settings())

    response = await _get(app, "/admin/dashboard", token=None)

    assert response.status_code == 200
    assert "AncoraMind" in response.text


async def test_dashboard_responses_carry_hardening_headers() -> None:
    app = _install(_settings())

    page = await _get(app, "/admin/dashboard", token=None)
    api = await _get(app, "/admin/dashboard/api/links")

    for response in (page, api):
        assert response.headers["x-frame-options"] == "DENY"
        assert response.headers["x-content-type-options"] == "nosniff"
        assert response.headers["referrer-policy"] == "no-referrer"
        assert response.headers["cache-control"] == "no-store"
        assert "frame-ancestors 'none'" in response.headers["content-security-policy"]


async def test_api_routes_reject_missing_or_wrong_token() -> None:
    app = _install(_settings())

    assert (await _get(app, "/admin/dashboard/api/links", token=None)).status_code == 401
    assert (await _get(app, "/admin/dashboard/api/links", token="wrong")).status_code == 401
    assert (
        await _get(app, "/admin/dashboard/api/runtime-config/status", token=None)
    ).status_code == 401


async def test_links_endpoint_hides_empty_urls_and_attaches_health_status() -> None:
    registry = HealthRegistry()
    registry.set_component("database", "healthy")
    app = _install(
        _settings(
            admin_link_supabase_url="https://supabase.example/project",
            admin_link_grafana_url="",
        ),
        health_registry=registry,
    )

    response = await _get(app, "/admin/dashboard/api/links")

    assert response.status_code == 200
    links = {link["name"]: link for link in response.json()["links"]}
    assert "Grafana" not in links
    assert links["Supabase"]["health_status"] == "healthy"


async def test_create_and_list_invitations_use_the_pairing_service_directly() -> None:
    service = AsyncMock()
    service.issue_invitation.return_value = IssuedPairingInvitation(
        invitation=_invitation(), code="one-time-code-with-sufficient-length"
    )
    service.list_invitations.return_value = [_invitation()]
    app = _install(_settings(), pairing_service=service)

    created = await _post(
        app, "/admin/dashboard/api/invitations", {"reason": "evaluator beta"}
    )
    listed = await _get(app, "/admin/dashboard/api/invitations")

    assert created.status_code == 201
    assert created.json()["code"] == "one-time-code-with-sufficient-length"
    assert "code_hash" not in created.json()["invitation"]
    assert service.issue_invitation.await_args.kwargs["actor"] == "operator"
    assert listed.status_code == 200
    assert listed.json()["invitations"][0]["status"] == "active"


async def test_runtime_config_status_and_validate_use_the_shared_manager() -> None:
    manager = _manager()
    app = _install(_settings(), manager=manager)

    status_response = await _get(app, "/admin/dashboard/api/runtime-config/status")
    valid_response = await _post(
        app,
        "/admin/dashboard/api/runtime-config/validate",
        {"config": manager.snapshot().config.model_dump(mode="json", by_alias=True)},
    )

    assert status_response.status_code == 200
    assert status_response.json()["source"] == "bootstrap"
    assert valid_response.status_code == 200
    assert valid_response.json()["valid"] is True


async def test_runtime_config_activate_maps_unknown_revision_to_404() -> None:
    manager = AsyncMock(spec=RuntimeConfigManager)
    manager.activate.side_effect = KeyError("Runtime config revision 99 does not exist")
    app = _install(_settings(), manager=manager)

    response = await _post(
        app,
        "/admin/dashboard/api/runtime-config/revisions/99/activate",
        {"expected_current_revision": 1, "reason": "promote"},
    )

    assert response.status_code == 404
