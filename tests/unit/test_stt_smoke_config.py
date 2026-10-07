"""Smoke gates are pure: no credentials, network or inference."""

from decimal import Decimal

import pytest

from scripts.stt_smoke_config import smoke_inputs, validate_external_key


def approved_env(tmp_path):
    audio = tmp_path / "synthetic.ogg"
    audio.write_bytes(b"OggSsynthetic")
    return {
        "ANCORA_STT_SMOKE_APPROVED": "1",
        "ANCORA_STT_SMOKE_SYNTHETIC": "1",
        "ANCORA_STT_SMOKE_PRIVACY_ACCEPTED": "1",
        "ANCORA_STT_SMOKE_TARIFF_VERIFIED": "1",
        "ANCORA_STT_SMOKE_AUDIO": str(audio),
        "ANCORA_STT_SMOKE_GATEWAY": "http://127.0.0.1:4000/v1",
        "ANCORA_STT_SMOKE_ALIAS": "stt-smoke-r1",
        "ANCORA_STT_SMOKE_RATE": "0.00000333",
        "ANCORA_STT_SMOKE_QUANTUM": "1",
        "ANCORA_STT_SMOKE_MINIMUM": "0",
        "ANCORA_STT_SMOKE_TARIFF_VERSION": "synthetic-test-r1",
        "ANCORA_STT_SMOKE_EXTERNAL_LIMIT": "1",
        "ANCORA_STT_SMOKE_DAILY_LIMIT": "0.1",
        "ANCORA_STT_SMOKE_MONTHLY_LIMIT": "0.5",
    }


def test_explicit_config(tmp_path):
    _, _, config = smoke_inputs(approved_env(tmp_path))
    assert config.speech.billing.maximum_estimate().estimated_cost_usd == Decimal("0.000999")
    assert config.execution_budget.max_model_calls == 1
    assert config.gateway.retries == config.gateway.cross_model_fallbacks == 0


@pytest.mark.parametrize(
    "name",
    [
        "APPROVED",
        "SYNTHETIC",
        "PRIVACY_ACCEPTED",
        "TARIFF_VERIFIED",
        "RATE",
        "QUANTUM",
        "MINIMUM",
        "TARIFF_VERSION",
        "ALIAS",
    ],
)
def test_missing_gate_or_tariff(tmp_path, name):
    env = approved_env(tmp_path)
    env.pop("ANCORA_STT_SMOKE_" + name)
    with pytest.raises(ValueError):
        smoke_inputs(env)


@pytest.mark.parametrize(
    "url",
    [
        "https://openrouter.ai/v1",
        "http://gateway.internal/v1",
        "http://key@localhost/v1",
        "http://localhost/v1?token=secret",
        "http://localhost/other",
    ],
)
def test_nonisolated_gateway_rejected(tmp_path, url):
    env = approved_env(tmp_path)
    env["ANCORA_STT_SMOKE_GATEWAY"] = url
    with pytest.raises(ValueError, match="local_gateway_required"):
        smoke_inputs(env)


def uncertain_env(tmp_path):
    env = approved_env(tmp_path)
    env.pop("ANCORA_STT_SMOKE_TARIFF_VERIFIED")
    env.update(
        {
            "ANCORA_STT_SMOKE_BILLING_UNCERTAINTY_ACCEPTED": "1",
            "ANCORA_STT_SMOKE_UPSTREAM_KEY_CONFIRMED": "1",
            "ANCORA_STT_SMOKE_MODEL": "openai/whisper-large-v3-turbo",
            "ANCORA_STT_SMOKE_RATE": "0.0001",
            "ANCORA_STT_SMOKE_MINIMUM": "300",
            "ANCORA_STT_SMOKE_TARIFF_VERSION": "smoke-estimate-unverified-r1",
        "ANCORA_STT_SMOKE_EXTERNAL_LIMIT": "0.05",
        "ANCORA_STT_SMOKE_DAILY_LIMIT": "0.05",
        "ANCORA_STT_SMOKE_MONTHLY_LIMIT": "0.05",
        }
    )
    return env


def test_uncertain_reserve_is_not_verified_tariff(tmp_path):
    env = uncertain_env(tmp_path)
    _, _, config = smoke_inputs(env)
    assert config.speech.billing.maximum_estimate().estimated_cost_usd == Decimal("0.03")
    assert "unverified" in config.speech.billing.version
    assert config.execution_budget.max_gateway_requests == 1


@pytest.mark.parametrize(
    "field,value",
    [
        ("BILLING_UNCERTAINTY_ACCEPTED", "0"),
        ("TARIFF_VERIFIED", "1"),
        ("UPSTREAM_KEY_CONFIRMED", "0"),
        ("MODEL", "other"),
        ("RATE", "0.00000333"),
        ("MINIMUM", "0"),
        ("QUANTUM", "NaN"),
        ("TARIFF_VERSION", "verified-r1"),
        ("EXTERNAL_LIMIT", "5"),
    ],
)
def test_uncertainty_cannot_bypass_gates(tmp_path, field, value):
    env = uncertain_env(tmp_path)
    env["ANCORA_STT_SMOKE_" + field] = value
    with pytest.raises(ValueError):
        smoke_inputs(env)


@pytest.mark.parametrize(
    "data",
    [
        {},
        {"limit": None, "limit_remaining": 1},
        {"limit": 5, "limit_remaining": 1},
        {"limit": "NaN", "limit_remaining": 1},
        {"limit": "0.05", "limit_remaining": "0.01"},
    ],
)
def test_external_key_must_have_real_limit_and_reserve(data):
    with pytest.raises(ValueError):
        validate_external_key(data, Decimal("0.05"))


def test_external_key_evidence():
    validate_external_key({"limit": "0.05", "limit_remaining": "0.05"}, Decimal("0.05"))
