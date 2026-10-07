"""Smoke gates are pure: no credentials, network or inference."""

from decimal import Decimal

import pytest

from scripts.stt_smoke_config import smoke_inputs


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
