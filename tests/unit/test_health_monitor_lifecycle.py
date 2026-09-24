"""Fail-open lifecycle tests for the Spec 016 health monitor."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI

from src.agent.health import HealthRegistry, install_health_monitor_lifespan, install_health_readiness_endpoint
from src.config import Settings


async def _readiness(app: FastAPI) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.get("/health/readiness")


async def _wait_for(condition: Callable[[], bool], *, timeout_seconds: float = 0.2) -> None:
    async def wait() -> None:
        while not condition():
            await asyncio.sleep(0.005)

    await asyncio.wait_for(wait(), timeout=timeout_seconds)


def _settings(**overrides: object) -> Settings:
    return Settings(
        ancora_database_url="postgresql+asyncpg://user:pass@localhost/db",
        health_probe_interval_seconds=5,
        **overrides,
    )


async def test_monitor_degrades_db_and_finished_worker_without_stopping_readiness(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = FastAPI()
    registry = HealthRegistry()
    install_health_readiness_endpoint(app, registry)
    monkeypatch.setattr("src.agent.health.get_telemetry", lambda: _Telemetry())

    async def unavailable_session() -> object:
        raise RuntimeError("postgres password=private")

    async def finished_worker() -> None:
        return None

    worker_task = asyncio.create_task(finished_worker())
    await worker_task
    app.state.reminder_worker_task = worker_task
    install_health_monitor_lifespan(
        app,
        _settings(),
        session_factory=unavailable_session,
        registry=registry,
    )

    async with app.router.lifespan_context(app):
        await _wait_for(lambda: "database" in registry.snapshot()["components"])
        response = await _readiness(app)

        assert response.status_code == 200
        payload = response.json()
        assert payload["components"]["database"]["status"] == "degraded"
        assert payload["components"]["reminder_worker"]["status"] == "degraded"
        assert not app.state.health_monitor_task.done()
        assert "password" not in response.text.lower()

    assert not hasattr(app.state, "health_monitor_task")


async def test_monitor_survives_an_unexpected_monitoring_dependency_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = FastAPI()
    registry = HealthRegistry()
    install_health_readiness_endpoint(app, registry)
    monkeypatch.setattr("src.agent.health.get_telemetry", lambda: _Telemetry())
    refresh_database = AsyncMock(side_effect=RuntimeError("unexpected monitor fault"))
    monkeypatch.setattr(registry, "refresh_database_and_queue", refresh_database)
    install_health_monitor_lifespan(
        app,
        _settings(),
        session_factory=AsyncMock(),
        registry=registry,
    )

    async with app.router.lifespan_context(app):
        await _wait_for(lambda: refresh_database.await_count == 1)
        response = await _readiness(app)

        assert response.status_code == 200
        assert not app.state.health_monitor_task.done()


async def test_monitor_marks_gateway_disabled_without_calling_its_probe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = FastAPI()
    registry = HealthRegistry()
    monkeypatch.setattr("src.agent.health.get_telemetry", lambda: _Telemetry())
    refresh_gateway = AsyncMock()
    monkeypatch.setattr(registry, "refresh_gateway", refresh_gateway)
    install_health_monitor_lifespan(
        app,
        _settings(ancora_database_url=""),
        session_factory=AsyncMock(),
        registry=registry,
    )

    async with app.router.lifespan_context(app):
        await _wait_for(lambda: "gateway" in registry.snapshot()["components"])

        assert registry.snapshot()["components"]["database"]["status"] == "disabled"
        assert registry.snapshot()["components"]["gateway"]["status"] == "disabled"
        refresh_gateway.assert_not_awaited()


class _Telemetry:
    def counter(self, *args: object, **kwargs: object) -> None:
        pass

    def gauge(self, *args: object, **kwargs: object) -> None:
        pass