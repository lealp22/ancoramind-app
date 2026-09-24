"""Unit tests for metadata-only readiness and health telemetry (specs/016)."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI

from src.agent.health import HealthRegistry, install_health_readiness_endpoint


class _Telemetry:
    def __init__(self) -> None:
        self.counters: list[tuple[str, int | float, dict[str, object] | None]] = []
        self.gauges: list[tuple[str, int | float, dict[str, object] | None]] = []

    def counter(
        self,
        name: str,
        value: int | float = 1,
        attributes: dict[str, object] | None = None,
    ) -> None:
        self.counters.append((name, value, attributes))

    def gauge(
        self,
        name: str,
        value: int | float,
        attributes: dict[str, object] | None = None,
    ) -> None:
        self.gauges.append((name, value, attributes))


async def _get(app: FastAPI) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.get("/health/readiness")


def test_registry_snapshot_contains_only_bounded_operational_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    telemetry = _Telemetry()
    monkeypatch.setattr("src.agent.health.get_telemetry", lambda: telemetry)
    registry = HealthRegistry()

    registry.heartbeat("reminder_worker")
    registry.set_component("gateway", "unknown")
    registry.set_circuit_state("unknown")
    registry.set_queue_depth(pending_global=3, max_per_chat=2)
    registry.set_runtime_config_revision(7, database_available=True)
    snapshot = registry.snapshot()

    assert snapshot["status"] == "ok"
    assert snapshot["components"]["reminder_worker"]["status"] == "healthy"
    assert snapshot["components"]["gateway"]["status"] == "unknown"
    assert snapshot["components"]["gateway_circuit"]["status"] == "unknown"
    assert snapshot["admission_queue"] == {"pending_global": 3, "max_pending_per_chat": 2}
    assert snapshot["runtime_config"] == {"active_revision": 7}
    assert snapshot["reminders"] == {"overdue": 0}
    assert "secret" not in str(snapshot).lower()
    assert telemetry.counters == [
        ("ancora.health.heartbeat", 1, {"ancora.health.component": "reminder_worker"})
    ]
    assert all("correlation" not in str(attributes) for _, _, attributes in telemetry.gauges)


def test_registry_rejects_unbounded_component_names(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("src.agent.health.get_telemetry", lambda: _Telemetry())

    with pytest.raises(ValueError, match="Unsupported health component"):
        HealthRegistry().set_component("telegram-chat-123", "healthy")


async def test_readiness_endpoint_is_informational_and_has_no_auth_or_secret_leakage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("src.agent.health.get_telemetry", lambda: _Telemetry())
    app = FastAPI()
    registry = HealthRegistry()
    registry.set_component("database", "degraded")
    install_health_readiness_endpoint(app, registry)

    response = await _get(app)

    assert response.status_code == 200
    assert response.json()["components"]["database"]["status"] == "degraded"
    assert "authorization" not in response.text.lower()
    assert "token" not in response.text.lower()


async def test_database_probe_marks_registry_degraded_without_exporting_error_detail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    telemetry = _Telemetry()
    monkeypatch.setattr("src.agent.health.get_telemetry", lambda: telemetry)
    registry = HealthRegistry()
    private_error = "postgres password=not-for-export"

    await registry.refresh_database_and_queue(AsyncMock(side_effect=RuntimeError(private_error)))

    assert registry.snapshot()["components"]["database"]["status"] == "degraded"
    assert private_error not in str(registry.snapshot())
    assert private_error not in str(telemetry.gauges)


async def test_readiness_does_not_do_database_io() -> None:
    app = FastAPI()
    registry = HealthRegistry()
    install_health_readiness_endpoint(app, registry)
    await asyncio.wait_for(_get(app), timeout=0.2)