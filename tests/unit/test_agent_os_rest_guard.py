"""Unit tests for the AgentOS REST-surface guard (specs/023 T1)."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.agent.agent_os_rest_guard import install_agent_os_rest_guard


def _app_with_guard(security_key: str = "secret-key") -> FastAPI:
    app = FastAPI()

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/telegram/webhook")
    async def telegram() -> dict[str, str]:
        return {"ok": "telegram"}

    @app.get("/admin/runtime-config")
    async def admin() -> dict[str, str]:
        return {"ok": "admin"}

    @app.get("/config")
    async def agno_config() -> dict[str, str]:
        return {"ok": "agno"}

    @app.get("/")
    async def root() -> dict[str, str]:
        return {"ok": "root"}

    install_agent_os_rest_guard(app, security_key)
    return app


class TestAgentOsRestGuard:
    def test_agno_route_rejected_without_credential(self) -> None:
        client = TestClient(_app_with_guard())
        response = client.get("/config")
        assert response.status_code == 401

    def test_agno_route_rejected_with_wrong_credential(self) -> None:
        client = TestClient(_app_with_guard())
        response = client.get("/config", headers={"Authorization": "Bearer wrong"})
        assert response.status_code == 401

    def test_agno_route_accepted_with_correct_credential(self) -> None:
        client = TestClient(_app_with_guard())
        response = client.get("/config", headers={"Authorization": "Bearer secret-key"})
        assert response.status_code == 200

    def test_ancoramind_owned_routes_stay_ungated(self) -> None:
        client = TestClient(_app_with_guard())
        assert client.get("/health").status_code == 200
        assert client.get("/telegram/webhook").status_code == 200
        assert client.get("/admin/runtime-config").status_code == 200
        assert client.get("/").status_code == 200
