"""Unit tests for closed, secret-free T6 runtime-config schemas."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

from src.domain.runtime_config.models import (
    RuntimeConfiguration,
    bootstrap_runtime_configuration,
    config_checksum,
    validate_runtime_config,
)


def _payload() -> dict[str, object]:
    return bootstrap_runtime_configuration().model_dump(mode="json", by_alias=True)


def test_bootstrap_is_valid_and_checksum_is_deterministic() -> None:
    payload = _payload()
    config = RuntimeConfiguration.model_validate(payload)
    reordered = deepcopy(payload)
    routing = reordered["routing"]
    assert isinstance(routing, dict)
    routes = routing["routes"]
    assert isinstance(routes, dict)
    routing["routes"] = dict(reversed(list(routes.items())))

    assert validate_runtime_config(payload).valid is True
    assert validate_runtime_config(reordered).valid is True
    assert config_checksum(config) == config_checksum(
        RuntimeConfiguration.model_validate(reordered)
    )


def test_bootstrap_keeps_the_guaranteed_base_alias_until_runtime_activation() -> None:
    config = bootstrap_runtime_configuration()

    assert config.routing.routes["ancoramind-default"].effective_gateway_route == (
        "ancoramind-default-r1"
    )


def test_gpt_6_luna_runtime_candidate_is_valid() -> None:
    candidate_path = (
        Path(__file__).parents[2]
        / "specs"
        / "013-llm-access-governance"
        / "configs"
        / "ancoramind-default-r3.json"
    )
    payload = json.loads(candidate_path.read_text(encoding="utf-8"))

    result = validate_runtime_config(payload)

    assert result.valid is True
    assert payload["routing"]["routes"]["ancoramind-default"]["effective_gateway_route"] == (
        "ancoramind-default-r3"
    )
    assert payload["pricing"]["routes"]["ancoramind-default-r3"] == {
        "input_cost_per_1m_usd": 0.1,
        "output_cost_per_1m_usd": 0.5,
    }


def test_schema_rejects_unknown_fields_at_any_depth() -> None:
    payload = _payload()
    routing = payload["routing"]
    assert isinstance(routing, dict)
    routing["unknown"] = True

    result = validate_runtime_config(payload)

    assert result.valid is False
    assert any("routing.unknown" in error for error in result.errors)


@pytest.mark.parametrize(
    ("path", "value", "expected"),
    [
        (("routing", "default_route"), "missing-route", "default_route must exist"),
        (("execution_budget", "max_gateway_requests"), 5, "at least max_model_calls"),
        (("execution_budget", "max_gateway_requests"), 20, "cannot exceed"),
        (("concurrency", "pending_global"), 1, "at least global"),
        (("admission", "user_burst"), 11, "cannot exceed user_requests_per_minute"),
        (("gateway", "request_timeout_seconds"), 121, "cannot exceed total runtime"),
    ],
)
def test_cross_field_invariants_fail_closed(
    path: tuple[str, str],
    value: object,
    expected: str,
) -> None:
    payload = _payload()
    section = payload[path[0]]
    assert isinstance(section, dict)
    section[path[1]] = value

    result = validate_runtime_config(payload)

    assert result.valid is False
    assert any(expected in error for error in result.errors)


@pytest.mark.parametrize("key", ["api_key", "access_token", "client-secret", "password"])
def test_sensitive_configuration_keys_are_rejected_without_false_positive(key: str) -> None:
    payload = _payload()
    gateway = payload["gateway"]
    assert isinstance(gateway, dict)
    gateway[key] = "must-never-persist"

    result = validate_runtime_config(payload)

    assert result.valid is False
    assert result.checksum is None
    assert any("sensitive configuration key" in error for error in result.errors)


def test_legitimate_token_budget_field_is_not_treated_as_a_secret() -> None:
    result = validate_runtime_config(_payload())

    assert result.valid is True
    assert result.checksum is not None


def test_pricing_is_optional_in_the_bootstrap_configuration() -> None:
    result = validate_runtime_config(_payload())

    assert result.valid is True
    config = RuntimeConfiguration.model_validate(_payload())
    assert config.pricing is None


def test_pricing_snapshot_validates_routes_and_prices() -> None:
    payload = _payload()
    payload["pricing"] = {
        "routes": {
            "ancoramind-default-r1": {
                "input_cost_per_1m_usd": 1.0,
                "output_cost_per_1m_usd": 2.0,
            }
        }
    }
    # T12: paid routes require the full cost-governance invariant (hard limit,
    # period budgets and a per-interaction cost ceiling).
    payload["cost_governance"] = {
        "external_hard_limit_usd": 20.0,
        "alert_threshold_pct": 60,
        "strong_alert_threshold_pct": 80,
        "hard_stop_threshold_pct": 90,
        "daily_budget_usd": 1.0,
        "monthly_budget_usd": 15.0,
        "route_monthly_budgets_usd": {},
    }
    payload["execution_budget"] = {
        **payload["execution_budget"],
        "max_estimated_cost_usd": 0.05,
    }

    result = validate_runtime_config(payload)

    assert result.valid is True
    config = RuntimeConfiguration.model_validate(payload)
    price = config.pricing.route_price("ancoramind-default-r1")
    assert price is not None
    assert price.input_cost_per_1m_usd == 1.0
    assert config.pricing.route_price("ancoramind-fast-r1") is None


def test_pricing_without_cost_governance_is_rejected() -> None:
    payload = _payload()
    payload["pricing"] = {
        "routes": {
            "ancoramind-default-r1": {
                "input_cost_per_1m_usd": 1.0,
                "output_cost_per_1m_usd": 2.0,
            }
        }
    }

    result = validate_runtime_config(payload)

    assert result.valid is False
    assert any("paid routes require cost governance" in error for error in result.errors)


def test_pricing_rejects_entries_without_any_price() -> None:
    payload = _payload()
    payload["pricing"] = {"routes": {"ancoramind-default-r1": {"input_cost_per_1m_usd": None}}}

    result = validate_runtime_config(payload)

    assert result.valid is False
    assert any("at least one token price" in error for error in result.errors)


def test_pricing_rejects_unknown_fields_and_negative_prices() -> None:
    payload = _payload()
    payload["pricing"] = {
        "routes": {
            "ancoramind-default-r1": {
                "input_cost_per_1m_usd": -1.0,
                "output_cost_per_1m_usd": 2.0,
            }
        }
    }
    result = validate_runtime_config(payload)
    assert result.valid is False

    payload = _payload()
    payload["pricing"] = {"routes": {"ancoramind-default-r1": {"api_key": "never"}}}
    result = validate_runtime_config(payload)
    assert result.valid is False
    assert any("sensitive configuration key" in error for error in result.errors)


def test_pricing_rejects_unknown_gateway_alias() -> None:
    payload = _payload()
    payload["pricing"] = {"routes": {"ancoramind-unknown-r1": {"input_cost_per_1m_usd": 1.0}}}

    result = validate_runtime_config(payload)

    assert result.valid is False
    assert any("pricing routes" in error for error in result.errors)


def test_tool_repeat_limit_requires_one_initial_successful_execution() -> None:
    payload = _payload()
    execution_budget = payload["execution_budget"]
    assert isinstance(execution_budget, dict)
    execution_budget["max_same_tool_args_after_success"] = 0

    result = validate_runtime_config(payload)

    assert result.valid is False
    assert any("max_same_tool_args_after_success" in error for error in result.errors)
