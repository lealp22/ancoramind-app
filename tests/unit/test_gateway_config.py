"""Regression tests for the LiteLLM Gateway pilot artefacts (T11/T12)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from scripts.litellm_create_virtual_key import (
    ALIASES,
    build_key_request_payload,
    resolve_aliases,
)

GATEWAY_DIR = Path(__file__).resolve().parents[2] / "gateway"


def _gateway_config() -> dict:
    return yaml.safe_load((GATEWAY_DIR / "litellm-config.yaml").read_text(encoding="utf-8"))


def test_gateway_exposes_exactly_the_versioned_ancoramind_aliases() -> None:
    names = [entry["model_name"] for entry in _gateway_config()["model_list"]]

    assert names == [
        "ancoramind-default-r1",
        "ancoramind-fast-r1",
        "ancoramind-vision-r1",
    ]


def test_gateway_reliability_policy_is_fail_closed() -> None:
    config = _gateway_config()
    router = config["router_settings"]

    assert router["num_retries"] == 0
    assert "fallbacks" not in config
    # T12 circuit breaker: cooldown a flaky deployment and fast-fail while open.
    assert router["allowed_fails"] == 3
    assert router["cooldown_time"] == 60


def test_gateway_route_capacity_limits_are_present_per_alias() -> None:
    for entry in _gateway_config()["model_list"]:
        assert entry["model_info"]["rpm"] > 0
        assert entry["model_info"]["tpm"] > 0


def test_gateway_config_contains_no_secrets() -> None:
    raw = (GATEWAY_DIR / "litellm-config.yaml").read_text(encoding="utf-8")

    assert "sk-" not in raw
    assert "os.environ/OPENROUTER_API_KEY" in raw
    assert "os.environ/LITELLM_MASTER_KEY" in raw


def test_gateway_dockerfile_pins_digest_and_disables_docs() -> None:
    raw = (GATEWAY_DIR / "Dockerfile").read_text(encoding="utf-8")

    assert "ghcr.io/berriai/litellm@sha256:" in raw
    for flag in ("NO_DOCS=True", "NO_REDOC=True", "NO_OPENAPI=True"):
        assert flag in raw
    cmd_lines = [line for line in raw.splitlines() if line.startswith("CMD")]
    assert len(cmd_lines) == 1
    # The image ENTRYPOINT is the litellm binary: CMD must not repeat it as argv[0].
    cmd = json.loads(cmd_lines[0][len("CMD ") :])
    assert cmd[0] != "litellm"
    assert "/app/litellm-config.yaml" in cmd


def test_virtual_key_payload_defaults_match_the_approved_limits() -> None:
    payload = build_key_request_payload({})

    assert payload["models"] == list(ALIASES)
    assert payload["rpm_limit"] == 60
    assert payload["tpm_limit"] == 250_000
    assert payload["max_parallel_requests"] == 4
    assert "max_budget" not in payload


def test_virtual_key_payload_honours_environment_overrides() -> None:
    payload = build_key_request_payload(
        {
            "LITELLM_VIRTUAL_KEY_RPM": "5",
            "LITELLM_VIRTUAL_KEY_TPM": "1000",
            "LITELLM_VIRTUAL_KEY_MAX_PARALLEL_REQUESTS": "2",
            "LITELLM_VIRTUAL_KEY_MAX_BUDGET_USD": "20",
            "LITELLM_VIRTUAL_KEY_BUDGET_DURATION": "1d",
        }
    )

    assert payload["rpm_limit"] == 5
    assert payload["tpm_limit"] == 1000
    assert payload["max_parallel_requests"] == 2
    assert payload["max_budget"] == 20.0
    assert payload["budget_duration"] == "1d"


def test_virtual_key_payload_rejects_invalid_limits() -> None:
    with pytest.raises(SystemExit, match="positive integer"):
        build_key_request_payload({"LITELLM_VIRTUAL_KEY_RPM": "0"})

    with pytest.raises(SystemExit, match="positive integer"):
        build_key_request_payload({"LITELLM_VIRTUAL_KEY_TPM": "fast"})


def test_gateway_enables_additive_model_publication() -> None:
    general = _gateway_config()["general_settings"]

    # ADR-005 amendment: aliases r2+ are published at runtime, so a physical
    # model change no longer requires a Gateway redeploy.
    assert general["store_model_in_db"] is True


def test_gateway_base_aliases_stay_versioned_and_immutable() -> None:
    from src.domain.runtime_config.models import GATEWAY_ROUTE_PATTERN

    for entry in _gateway_config()["model_list"]:
        alias = entry["model_name"]
        # Base aliases are the r1 generation declared in Git; they are never
        # edited in place, and every new generation is a separate alias.
        assert GATEWAY_ROUTE_PATTERN.fullmatch(alias)
        assert alias.endswith("-r1")


def test_virtual_key_allowlist_defaults_to_the_base_aliases() -> None:
    assert resolve_aliases({}) == list(ALIASES)
    assert build_key_request_payload({})["models"] == list(ALIASES)


def test_virtual_key_allowlist_accepts_a_published_alias() -> None:
    aliases = resolve_aliases({"LITELLM_VIRTUAL_KEY_ALIASES": "ancoramind-default-r2"})

    assert aliases == [*ALIASES, "ancoramind-default-r2"]


def test_virtual_key_allowlist_rejects_unversioned_entries() -> None:
    with pytest.raises(SystemExit, match="versioned alias"):
        resolve_aliases({"LITELLM_VIRTUAL_KEY_ALIASES": "ancoramind-default"})
