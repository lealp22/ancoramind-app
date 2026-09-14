"""Unit tests for cost-governance invariants and evaluation (specs/013 T12)."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

import src.domain.llm_access.cost_governance as cost_governance_module
from src.domain.llm_access.cost_governance import (
    CostGovernanceError,
    SpendSummary,
    evaluate_cost_governance,
)
from src.domain.runtime_config.models import (
    CostGovernanceConfig,
    RuntimeConfiguration,
    bootstrap_runtime_configuration,
)

_COST_GOVERNANCE: dict[str, Any] = {
    "external_hard_limit_usd": 20.0,
    "alert_threshold_pct": 60,
    "strong_alert_threshold_pct": 80,
    "hard_stop_threshold_pct": 90,
    "daily_budget_usd": 1.0,
    "monthly_budget_usd": 15.0,
    "route_monthly_budgets_usd": {"ancoramind-default": 10.0},
}


def _config_payload() -> dict[str, Any]:
    return bootstrap_runtime_configuration().model_dump(mode="json", by_alias=True)


def _config_with_cost_governance(**overrides: Any) -> RuntimeConfiguration:
    governance = {**_COST_GOVERNANCE, **overrides}
    return RuntimeConfiguration.model_validate({**_config_payload(), "cost_governance": governance})


class _FakeTelemetry:
    def __init__(self) -> None:
        self.counters: list[tuple[str, dict[str, str] | None]] = []

    def counter(self, name: str, attributes: dict[str, str] | None = None, **_: Any) -> None:
        self.counters.append((name, attributes))


@pytest.fixture
def telemetry(monkeypatch: pytest.MonkeyPatch) -> _FakeTelemetry:
    fake = _FakeTelemetry()
    monkeypatch.setattr(cost_governance_module, "get_telemetry", lambda: fake)
    return fake


def test_bootstrap_config_has_no_cost_governance_and_enforces_nothing() -> None:
    config = bootstrap_runtime_configuration()

    assert config.cost_governance is None

    evaluate_cost_governance(
        config, SpendSummary(today_usd=999.0, month_usd=999.0, route_month_usd={})
    )


def test_cost_governance_thresholds_must_be_strictly_increasing() -> None:
    with pytest.raises(ValidationError, match="strictly increasing"):
        _config_with_cost_governance(alert_threshold_pct=80, strong_alert_threshold_pct=60)


def test_period_budgets_cannot_exceed_the_external_hard_limit() -> None:
    with pytest.raises(ValidationError, match="daily_budget_usd cannot exceed"):
        _config_with_cost_governance(daily_budget_usd=25.0)

    with pytest.raises(ValidationError, match="external hard limit"):
        CostGovernanceConfig.model_validate(
            {**_COST_GOVERNANCE, "route_monthly_budgets_usd": {"ancoramind-default": 21.0}}
        )


def test_paid_routes_require_pricing_cost_governance_and_ceilings() -> None:
    payload = _config_payload()
    payload["pricing"] = {
        "routes": {
            "ancoramind-default-r1": {
                "input_cost_per_1m_usd": 0.15,
                "output_cost_per_1m_usd": 0.6,
            }
        }
    }

    payload["cost_governance"] = {
        **_COST_GOVERNANCE,
        "daily_budget_usd": None,
        "monthly_budget_usd": None,
    }
    with pytest.raises(ValidationError, match="paid routes require daily and monthly"):
        RuntimeConfiguration.model_validate(payload)

    payload["cost_governance"] = {**_COST_GOVERNANCE}
    with pytest.raises(
        ValidationError, match="paid routes require a per-interaction estimated-cost"
    ):
        RuntimeConfiguration.model_validate(payload)

    payload["execution_budget"] = {
        **payload["execution_budget"],
        "max_estimated_cost_usd": 0.05,
    }
    paid = RuntimeConfiguration.model_validate(payload)
    assert paid.cost_governance is not None
    assert paid.cost_governance.monthly_budget_usd == 15.0


def test_route_budgets_must_reference_configured_routes() -> None:
    with pytest.raises(ValidationError, match="route budgets must reference"):
        _config_with_cost_governance(route_monthly_budgets_usd={"ancoramind-unknown": 1.0})


def test_hard_stop_at_90_percent_of_the_external_limit(telemetry: _FakeTelemetry) -> None:
    config = _config_with_cost_governance()

    with pytest.raises(CostGovernanceError) as exc_info:
        evaluate_cost_governance(config, SpendSummary(today_usd=0.1, month_usd=18.0))

    assert exc_info.value.limit == "external_monthly_hard_stop"
    assert (
        "ancora.cost_governance.hard_stop",
        {"ancora.cost.limit": "external_monthly_hard_stop"},
    ) in telemetry.counters


def test_alerts_fire_at_60_and_80_percent_of_the_external_limit(
    telemetry: _FakeTelemetry,
) -> None:
    config = _config_with_cost_governance(monthly_budget_usd=17.0)

    evaluate_cost_governance(config, SpendSummary(today_usd=0.1, month_usd=12.0))
    assert telemetry.counters == [
        (
            "ancora.cost_governance.alert",
            {"ancora.cost.threshold_pct": "60", "ancora.cost.period": "month"},
        )
    ]

    telemetry.counters.clear()
    evaluate_cost_governance(config, SpendSummary(today_usd=0.1, month_usd=16.0))
    assert telemetry.counters == [
        (
            "ancora.cost_governance.alert",
            {"ancora.cost.threshold_pct": "80", "ancora.cost.period": "month"},
        )
    ]


def test_daily_budget_exhaustion_blocks_the_run(telemetry: _FakeTelemetry) -> None:
    config = _config_with_cost_governance()

    with pytest.raises(CostGovernanceError) as exc_info:
        evaluate_cost_governance(config, SpendSummary(today_usd=1.0, month_usd=1.0))

    assert exc_info.value.limit == "daily_budget_exhausted"


def test_monthly_budget_exhaustion_blocks_the_run(telemetry: _FakeTelemetry) -> None:
    config = _config_with_cost_governance()

    with pytest.raises(CostGovernanceError) as exc_info:
        evaluate_cost_governance(config, SpendSummary(today_usd=0.5, month_usd=15.0))

    assert exc_info.value.limit == "monthly_budget_exhausted"


def test_route_monthly_budget_exhaustion_blocks_the_run(telemetry: _FakeTelemetry) -> None:
    config = _config_with_cost_governance()

    with pytest.raises(CostGovernanceError) as exc_info:
        evaluate_cost_governance(
            config,
            SpendSummary(
                today_usd=0.5, month_usd=10.0, route_month_usd={"ancoramind-default": 10.0}
            ),
        )

    assert exc_info.value.limit == "route_monthly_budget_exhausted"


def test_healthy_spend_does_not_block_or_alert(telemetry: _FakeTelemetry) -> None:
    config = _config_with_cost_governance()

    evaluate_cost_governance(
        config,
        SpendSummary(
            today_usd=0.2,
            month_usd=5.0,
            route_month_usd={"ancoramind-default": 3.0},
        ),
    )

    assert telemetry.counters == []


def test_route_budgets_require_logical_route_names() -> None:
    with pytest.raises(ValidationError, match="logical route names"):
        CostGovernanceConfig.model_validate(
            {**_COST_GOVERNANCE, "route_monthly_budgets_usd": {"Default!": 1.0}}
        )
