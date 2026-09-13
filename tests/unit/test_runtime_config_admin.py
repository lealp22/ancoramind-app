"""Unit tests for T6 protected runtime-config admin API wiring and auth gates."""

from __future__ import annotations

from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI

from src.agent.runtime_config_admin import (
    create_runtime_config_manager,
    install_runtime_config_admin_api,
    validate_runtime_config_admin_settings,
)
from src.config import Settings
from src.domain.runtime_config.models import bootstrap_runtime_configuration
from src.domain.runtime_config.service import RuntimeConfigManager


def _settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "ancora_database_url": "postgresql+asyncpg://user:pass@localhost/db",
        "runtime_config_admin_enabled": True,
        "runtime_config_admin_token": "admin-secret",
    }
    values.update(overrides)
    return Settings(**values)


async def _get(app: FastAPI, path: str, *, token: str | None = None) -> httpx.Response:
    headers = {"authorization": f"Bearer {token}"} if token else {}
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.get(path, headers=headers)


@pytest.mark.parametrize(
    ("override", "expected_name"),
    [
        ({"ancora_database_url": ""}, "ANCORA_DATABASE_URL"),
        ({"runtime_config_admin_token": ""}, "RUNTIME_CONFIG_ADMIN_TOKEN"),
    ],
)
def test_enabled_admin_requires_security_prerequisites(
    override: dict[str, object],
    expected_name: str,
) -> None:
    with pytest.raises(ValueError, match=expected_name):
        validate_runtime_config_admin_settings(_settings(**override))


async def test_admin_api_is_not_installed_when_disabled() -> None:
    app = FastAPI()
    settings = _settings(runtime_config_admin_enabled=False)
    manager = RuntimeConfigManager(
        session_factory=AsyncMock(),
        bootstrap=bootstrap_runtime_configuration(),
    )

    install_runtime_config_admin_api(app, settings, manager)

    response = await _get(app, "/admin/runtime-config/status", token="admin-secret")
    assert response.status_code == 404


async def test_admin_status_requires_valid_bearer_and_does_not_expose_secret() -> None:
    app = FastAPI()
    manager = RuntimeConfigManager(
        session_factory=AsyncMock(),
        bootstrap=bootstrap_runtime_configuration(),
    )
    install_runtime_config_admin_api(app, _settings(), manager)

    assert (await _get(app, "/admin/runtime-config/status")).status_code == 401
    assert (await _get(app, "/admin/runtime-config/status", token="wrong")).status_code == 401

    response = await _get(app, "/admin/runtime-config/status", token="admin-secret")
    assert response.status_code == 200
    assert response.json()["source"] == "bootstrap"
    assert "admin-secret" not in response.text


def test_manager_factory_uses_configured_bootstrap_route() -> None:
    manager = create_runtime_config_manager(
        _settings(runtime_config_bootstrap_default_route="ancoramind-fast"),
        AsyncMock(),
    )

    assert manager.snapshot().config.routing.default_route == "ancoramind-fast"
