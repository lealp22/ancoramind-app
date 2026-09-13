"""Unit tests for closed, secret-free T6 runtime-config schemas."""

from __future__ import annotations

from copy import deepcopy

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
