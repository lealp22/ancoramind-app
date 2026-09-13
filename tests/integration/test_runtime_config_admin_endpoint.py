"""HTTP integration tests for the protected T6 runtime-config control plane."""

from __future__ import annotations

from copy import deepcopy

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession

from src.agent.runtime_config_admin import install_runtime_config_admin_api
from src.config import Settings
from src.domain.runtime_config.models import bootstrap_runtime_configuration
from src.domain.runtime_config.service import RuntimeConfigManager
from src.repositories.database import get_session

pytestmark = pytest.mark.integration

TOKEN = "admin-test-token"
ACTOR = "operator@example.test"


def _settings() -> Settings:
    return Settings(
        ancora_database_url="postgresql+asyncpg://user:pass@localhost/db",
        runtime_config_admin_enabled=True,
        runtime_config_admin_token=TOKEN,
    )


def _payload(default_route: str = "ancoramind-default") -> dict[str, object]:
    return bootstrap_runtime_configuration(default_route).model_dump(mode="json", by_alias=True)


async def _request(
    app: FastAPI,
    method: str,
    path: str,
    *,
    body: object | None = None,
    token: str = TOKEN,
    actor: str | None = ACTOR,
) -> httpx.Response:
    headers = {"authorization": f"Bearer {token}"}
    if actor is not None:
        headers["x-ancora-admin-actor"] = actor
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.request(method, path, json=body, headers=headers)


async def _app() -> tuple[FastAPI, RuntimeConfigManager]:
    manager = RuntimeConfigManager(
        session_factory=get_session,
        bootstrap=bootstrap_runtime_configuration(),
    )
    await manager.initialize()
    app = FastAPI()
    install_runtime_config_admin_api(app, _settings(), manager)
    return app, manager


async def test_admin_api_validates_publishes_activates_and_rolls_back(
    session: AsyncSession,
) -> None:
    app, manager = await _app()
    status_response = await _request(app, "GET", "/admin/runtime-config/status")
    assert status_response.status_code == 200
    assert status_response.json()["active_revision"] == 1
    assert status_response.json()["database_available"] is True

    invalid = deepcopy(_payload())
    gateway = invalid["gateway"]
    assert isinstance(gateway, dict)
    gateway["api_key"] = "never-persist"
    validation_response = await _request(
        app,
        "POST",
        "/admin/runtime-config/validate",
        body={"config": invalid},
    )
    assert validation_response.status_code == 200
    assert validation_response.json()["valid"] is False

    invalid_create = await _request(
        app,
        "POST",
        "/admin/runtime-config/revisions",
        body={"config": invalid, "reason": "invalid must not persist"},
    )
    assert invalid_create.status_code == 422
    assert "never-persist" not in invalid_create.text

    candidate = _payload("ancoramind-fast")
    created = await _request(
        app,
        "POST",
        "/admin/runtime-config/revisions",
        body={"config": candidate, "reason": "use fast route"},
    )
    assert created.status_code == 201
    revision = created.json()["revision"]
    assert created.json()["created_by"] == ACTOR

    missing_actor = await _request(
        app,
        "POST",
        f"/admin/runtime-config/revisions/{revision}/activate",
        body={"expected_current_revision": 1, "reason": "activate"},
        actor=None,
    )
    assert missing_actor.status_code == 422

    activated = await _request(
        app,
        "POST",
        f"/admin/runtime-config/revisions/{revision}/activate",
        body={"expected_current_revision": 1, "reason": "activate fast route"},
    )
    assert activated.status_code == 200
    assert activated.json()["active_revision"] == revision
    assert manager.snapshot().revision == revision
    assert manager.snapshot().config.routing.default_route == "ancoramind-fast"

    conflict = await _request(
        app,
        "POST",
        f"/admin/runtime-config/revisions/{revision}/activate",
        body={"expected_current_revision": 1, "reason": "stale activation"},
    )
    assert conflict.status_code == 409

    rollback = await _request(
        app,
        "POST",
        "/admin/runtime-config/rollback",
        body={
            "revision": 1,
            "expected_current_revision": revision,
            "reason": "restore bootstrap",
        },
    )
    assert rollback.status_code == 200
    assert rollback.json()["active_revision"] == 1
    assert manager.snapshot().revision == 1


async def test_admin_api_rejects_bad_auth_extra_fields_and_unavailable_control_plane(
    session: AsyncSession,
) -> None:
    app, _ = await _app()

    unauthorized = await _request(
        app,
        "POST",
        "/admin/runtime-config/validate",
        body={"config": _payload()},
        token="wrong-token",
    )
    assert unauthorized.status_code == 401

    extra_field = await _request(
        app,
        "POST",
        "/admin/runtime-config/validate",
        body={"config": _payload(), "unexpected": True},
    )
    assert extra_field.status_code == 422

    unavailable_manager = RuntimeConfigManager(
        session_factory=get_session,
        bootstrap=bootstrap_runtime_configuration(),
    )
    unavailable_app = FastAPI()
    install_runtime_config_admin_api(unavailable_app, _settings(), unavailable_manager)
    unavailable = await _request(
        unavailable_app,
        "POST",
        "/admin/runtime-config/revisions",
        body={"config": _payload(), "reason": "database has not initialized"},
    )
    assert unavailable.status_code == 503
