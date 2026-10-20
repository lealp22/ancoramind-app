"""Unit tests for the FinOps/quality dashboard routes (specs/043 T6)."""

from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI

from src.agent.admin_dashboard import install_admin_dashboard
from src.agent.health import HealthRegistry
from src.config import Settings
from src.domain.finops.models import (
    CostTotals,
    LatencyStats,
    ProposalOutcome,
    UserCost,
)
from src.domain.finops.service import FinopsService
from src.domain.llm_access.cost_governance import SpendSummary
from src.domain.runtime_config.models import bootstrap_runtime_configuration
from src.domain.runtime_config.service import RuntimeConfigManager

TOKEN = "dashboard-secret"
PATHS = ("/admin/dashboard/api/finops", "/admin/dashboard/api/quality")


def _settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "ancora_database_url": "postgresql+asyncpg://user:pass@localhost/db",
        "admin_dashboard_enabled": True,
        "admin_dashboard_token": TOKEN,
        "telegram_pairing_code_pepper": "pairing-pepper",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def _reader() -> AsyncMock:
    reader = AsyncMock()
    reader.totals.return_value = CostTotals(cost_usd=2.5, calls=3)
    reader.daily.return_value = []
    reader.by_user.return_value = [
        ("918273645", UserCost(user="", cost_usd=2.5, total_tokens=9, calls=3, interactions=2))
    ]
    reader.by_route_model.return_value = []
    reader.by_cost_source.return_value = []
    reader.interactions_by_status.return_value = []
    reader.tool_calls_total.return_value = 4
    reader.proposals.return_value = [
        ProposalOutcome(tool_name="create_note", status="executed", consent_mode="x", count=3)
    ]
    reader.latency.return_value = LatencyStats()
    return reader


class _Manager:
    def __init__(self, cost_governance: object | None) -> None:
        self._snapshot = SimpleNamespace(config=SimpleNamespace(cost_governance=cost_governance))

    def snapshot(self) -> SimpleNamespace:
        return self._snapshot


def _app(
    settings: Settings,
    *,
    reader: AsyncMock | None = None,
    governance: object | None = None,
    spend: SpendSummary | None = None,
) -> FastAPI:
    app = FastAPI()
    spend_reader = AsyncMock()
    spend_reader.summarize_spend.return_value = spend or SpendSummary()
    install_admin_dashboard(
        app,
        settings,
        AsyncMock(return_value=AsyncMock()),
        health_registry=HealthRegistry(),
        runtime_config_manager=_Manager(governance),  # type: ignore[arg-type]
        finops_service_factory=lambda _s: FinopsService(
            reader or _reader(), pseudonym_key="pairing-pepper"
        ),
        spend_reader_factory=lambda _s: spend_reader,
    )
    return app


async def _get(app: FastAPI, path: str, *, token: str | None = TOKEN) -> httpx.Response:
    headers = {"authorization": f"Bearer {token}"} if token is not None else {}
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.get(path, headers=headers)


@pytest.mark.parametrize("path", PATHS)
@pytest.mark.parametrize("token", [None, "wrong", "pairing-pepper"])
async def test_routes_require_the_dashboard_token(path: str, token: str | None) -> None:
    reader = _reader()
    response = await _get(_app(_settings(), reader=reader), path, token=token)
    assert response.status_code == 401
    reader.totals.assert_not_called()
    reader.proposals.assert_not_called()


@pytest.mark.parametrize("path", PATHS)
@pytest.mark.parametrize("days", ["0", "91", "-3", "abc", ""])
async def test_routes_reject_invalid_windows_without_reading(path: str, days: str) -> None:
    reader = _reader()
    response = await _get(_app(_settings(), reader=reader), f"{path}?days={days}")
    assert response.status_code == 422
    reader.totals.assert_not_called()
    reader.proposals.assert_not_called()


@pytest.mark.parametrize("path", PATHS)
async def test_routes_are_absent_when_dashboard_is_disabled(path: str) -> None:
    app = _app(_settings(admin_dashboard_enabled=False))
    assert (await _get(app, path)).status_code == 404


async def test_finops_route_pseudonymises_users_and_defaults_to_30_days() -> None:
    response = await _get(_app(_settings()), PATHS[0])
    assert response.status_code == 200
    body = response.json()
    assert body["days"] == 30
    assert body["totals"]["cost_usd"] == 2.5
    assert body["by_user"][0]["user"].startswith("u-")
    assert "918273645" not in response.text
    assert response.headers["cache-control"] == "no-store"


async def test_finops_budget_is_null_without_cost_governance() -> None:
    body = (await _get(_app(_settings(), governance=None), PATHS[0])).json()
    assert body["budget"] is None


async def test_finops_budget_uses_governance_limits_and_ledger_spend() -> None:
    governance = SimpleNamespace(monthly_budget_usd=10.0, daily_budget_usd=2.0)
    app = _app(
        _settings(),
        governance=governance,
        spend=SpendSummary(today_usd=1.0, month_usd=5.0),
    )
    budget = (await _get(app, PATHS[0])).json()["budget"]
    assert budget["month_used_pct"] == 50.0
    assert budget["day_used_pct"] == 50.0
    assert budget["monthly_budget_usd"] == 10.0


async def test_quality_route_returns_rates_and_no_identifiers() -> None:
    response = await _get(_app(_settings()), PATHS[1] + "?days=7")
    assert response.status_code == 200
    body = response.json()
    assert body["days"] == 7
    assert body["proposal_rates"]["executed_rate"] == 1.0
    for field in ("telegram_user_id", "chat_id", "agno_session_id"):
        assert field not in response.text


def test_default_wiring_registers_both_routes() -> None:
    app = FastAPI()
    install_admin_dashboard(
        app,
        _settings(),
        AsyncMock(),
        health_registry=HealthRegistry(),
        runtime_config_manager=RuntimeConfigManager(
            session_factory=AsyncMock(), bootstrap=bootstrap_runtime_configuration()
        ),
    )
    assert {getattr(r, "path", "") for r in app.routes} >= set(PATHS)


HTML = Path(__file__).parents[2] / "src" / "agent" / "admin_dashboard_static" / "dashboard.html"


def _finops_js() -> str:
    source = HTML.read_text(encoding="utf-8")
    start = source.index("// ---- FinOps y calidad")
    end = source.index("async function loadFinops")
    block = source[start:end]
    return "\n".join(line for line in block.splitlines() if not line.lstrip().startswith("//"))


def test_finops_ui_never_writes_server_data_as_html() -> None:
    js = _finops_js()
    for sink in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval("):
        assert sink not in js, sink


def test_dashboard_loads_no_external_resources() -> None:
    source = HTML.read_text(encoding="utf-8")
    assert not re.search(r"""(src|href)=["']https?://""", source)
    assert "@import" not in source and "<link" not in source


def test_finops_panel_is_loaded_on_login_and_states_exclusions() -> None:
    source = HTML.read_text(encoding="utf-8")
    assert "loadFinops();" in source.split("function enterApp()")[1].split("}")[0]
    assert 'id="fo-excluded"' in source
