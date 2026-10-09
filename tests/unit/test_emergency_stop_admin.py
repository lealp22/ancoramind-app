"""Unit tests for the emergency-stop admin API wiring and auth gate (BL-44/specs/031)."""

from __future__ import annotations

import httpx
import pytest
from fastapi import FastAPI

from src.agent.emergency_stop_admin import install_emergency_stop_admin_api
from src.config import Settings
from src.domain.emergency_stop.service import EmergencyStopManager


def _settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "runtime_config_admin_enabled": True,
        "runtime_config_admin_token": "admin-secret",
    }
    values.update(overrides)
    return Settings(**values)


async def _request(
    app: FastAPI,
    method: str,
    path: str,
    *,
    token: str | None = None,
    actor: str | None = None,
    json: dict[str, object] | None = None,
) -> httpx.Response:
    headers = {}
    if token:
        headers["authorization"] = f"Bearer {token}"
    if actor:
        headers["x-ancora-admin-actor"] = actor
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.request(method, path, headers=headers, json=json)


async def test_admin_api_is_not_installed_when_disabled() -> None:
    app = FastAPI()
    settings = _settings(runtime_config_admin_enabled=False)
    manager = EmergencyStopManager()

    install_emergency_stop_admin_api(app, settings, manager)

    response = await _request(app, "GET", "/admin/emergency-stop/status", token="admin-secret")
    assert response.status_code == 404


async def test_status_requires_valid_bearer_and_does_not_expose_secret() -> None:
    app = FastAPI()
    manager = EmergencyStopManager()
    install_emergency_stop_admin_api(app, _settings(), manager)

    assert (await _request(app, "GET", "/admin/emergency-stop/status")).status_code == 401
    assert (
        await _request(app, "GET", "/admin/emergency-stop/status", token="wrong")
    ).status_code == 401

    response = await _request(
        app, "GET", "/admin/emergency-stop/status", token="admin-secret"
    )
    assert response.status_code == 200
    assert response.json() == {
        "active": False,
        "reason": None,
        "activated_by": None,
        "activated_at": None,
    }
    assert "admin-secret" not in response.text


async def test_activate_then_deactivate_round_trip() -> None:
    app = FastAPI()
    manager = EmergencyStopManager()
    install_emergency_stop_admin_api(app, _settings(), manager)

    activate_response = await _request(
        app,
        "POST",
        "/admin/emergency-stop/activate",
        token="admin-secret",
        actor="jesus",
        json={"reason": "cost spike"},
    )
    assert activate_response.status_code == 200
    body = activate_response.json()
    assert body["active"] is True
    assert body["reason"] == "cost spike"
    assert body["activated_by"] == "jesus"
    assert manager.current().active is True

    status_response = await _request(
        app, "GET", "/admin/emergency-stop/status", token="admin-secret"
    )
    assert status_response.json()["active"] is True

    deactivate_response = await _request(
        app,
        "POST",
        "/admin/emergency-stop/deactivate",
        token="admin-secret",
        actor="jesus",
        json={"reason": "resolved"},
    )
    assert deactivate_response.status_code == 200
    assert deactivate_response.json()["active"] is False
    assert manager.current().active is False


@pytest.mark.parametrize("path", ["activate", "deactivate"])
async def test_activate_requires_actor_header(path: str) -> None:
    app = FastAPI()
    manager = EmergencyStopManager()
    install_emergency_stop_admin_api(app, _settings(), manager)

    response = await _request(
        app,
        "POST",
        f"/admin/emergency-stop/{path}",
        token="admin-secret",
        json={"reason": "cost spike"},
    )
    assert response.status_code == 422


@pytest.mark.parametrize("path", ["activate", "deactivate"])
async def test_blank_reason_is_rejected(path: str) -> None:
    app = FastAPI()
    manager = EmergencyStopManager()
    install_emergency_stop_admin_api(app, _settings(), manager)

    response = await _request(
        app,
        "POST",
        f"/admin/emergency-stop/{path}",
        token="admin-secret",
        actor="jesus",
        json={"reason": "   "},
    )
    assert response.status_code == 422
