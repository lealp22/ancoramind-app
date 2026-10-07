"""Validate explicit smoke approval/configuration without network or inference."""

from collections.abc import Mapping
from pathlib import Path
from urllib.parse import urlsplit

from src.domain.runtime_config.models import RuntimeConfiguration, bootstrap_runtime_configuration
from src.domain.speech.models import MAX_VOICE_BYTES


def smoke_inputs(env: Mapping[str, str]) -> tuple[Path, str, RuntimeConfiguration]:
    """Fail closed: synthetic data, privacy acceptance, tariff and local Gateway only.

    This is an isolated test configuration, not a publish/activation operation.
    Credentials are never accepted here or returned in diagnostic messages.
    """
    for name in (
        "ANCORA_STT_SMOKE_APPROVED",
        "ANCORA_STT_SMOKE_SYNTHETIC",
        "ANCORA_STT_SMOKE_PRIVACY_ACCEPTED",
        "ANCORA_STT_SMOKE_TARIFF_VERIFIED",
    ):
        if env.get(name) != "1":
            raise ValueError("stt_smoke_approval_required")
    audio = Path(env.get("ANCORA_STT_SMOKE_AUDIO", ""))
    if not audio.is_absolute() or not audio.is_file():
        raise ValueError("stt_smoke_audio_required")
    if not 0 < audio.stat().st_size <= MAX_VOICE_BYTES:
        raise ValueError("stt_smoke_audio_size_invalid")
    gateway = env.get("ANCORA_STT_SMOKE_GATEWAY", "")
    parsed = urlsplit(gateway)
    if (
        parsed.scheme != "http"
        or parsed.hostname not in {"localhost", "127.0.0.1", "::1"}
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.path.rstrip("/") != "/v1"
    ):
        raise ValueError("stt_smoke_local_gateway_required")
    required = (
        "ANCORA_STT_SMOKE_ALIAS",
        "ANCORA_STT_SMOKE_RATE",
        "ANCORA_STT_SMOKE_QUANTUM",
        "ANCORA_STT_SMOKE_MINIMUM",
        "ANCORA_STT_SMOKE_TARIFF_VERSION",
        "ANCORA_STT_SMOKE_EXTERNAL_LIMIT",
        "ANCORA_STT_SMOKE_DAILY_LIMIT",
        "ANCORA_STT_SMOKE_MONTHLY_LIMIT",
    )
    if any(not env.get(name) for name in required):
        raise ValueError("stt_smoke_tariff_required")
    payload = bootstrap_runtime_configuration().model_dump(mode="json", by_alias=True)
    payload["routing"]["routes"]["stt-smoke"] = {
        "effective_gateway_route": env["ANCORA_STT_SMOKE_ALIAS"],
        "capabilities": ["transcription"],
    }
    payload["speech"] = {
        "logical_route": "stt-smoke",
        "billing": {
            "version": env["ANCORA_STT_SMOKE_TARIFF_VERSION"],
            "rate_usd_per_second": env["ANCORA_STT_SMOKE_RATE"],
            "quantum_seconds": env["ANCORA_STT_SMOKE_QUANTUM"],
            "minimum_seconds": env["ANCORA_STT_SMOKE_MINIMUM"],
        },
    }
    payload["gateway"]["request_timeout_seconds"] = 60
    payload["cost_governance"] = {
        "external_hard_limit_usd": env["ANCORA_STT_SMOKE_EXTERNAL_LIMIT"],
        "daily_budget_usd": env["ANCORA_STT_SMOKE_DAILY_LIMIT"],
        "monthly_budget_usd": env["ANCORA_STT_SMOKE_MONTHLY_LIMIT"],
        "alert_threshold_pct": 60,
        "strong_alert_threshold_pct": 80,
        "hard_stop_threshold_pct": 90,
    }
    payload["execution_budget"]["max_model_calls"] = 1
    payload["execution_budget"]["max_gateway_requests"] = 1
    payload["execution_budget"]["max_gateway_attempts_per_model_call"] = 1
    return audio, gateway, RuntimeConfiguration.model_validate(payload)
