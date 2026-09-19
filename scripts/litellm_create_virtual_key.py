"""Create one AncoraMind-only LiteLLM virtual key after the T11 proxy is healthy.

Usage (PowerShell):
  $env:LITELLM_PROXY_ADMIN_URL='http://localhost:4000'
  $env:LITELLM_MASTER_KEY='sk-...'
  python scripts/litellm_create_virtual_key.py

Optional T12 limits (defaults shown):
  $env:LITELLM_VIRTUAL_KEY_RPM='60'
  $env:LITELLM_VIRTUAL_KEY_TPM='250000'
  $env:LITELLM_VIRTUAL_KEY_MAX_PARALLEL_REQUESTS='4'
  $env:LITELLM_VIRTUAL_KEY_MAX_BUDGET_USD='20'      # Gateway-side backstop (USD)
  $env:LITELLM_VIRTUAL_KEY_BUDGET_DURATION='30d'    # reset window

Optional alias extension (ADR-005 amendment). The base aliases are always
included; add newly published versioned aliases so the key can call them:
  $env:LITELLM_VIRTUAL_KEY_ALIASES='ancoramind-default-r2'

Over time prefer ``scripts/litellm_gateway_alias.py grant``, which extends the
allowlist of an existing key without recreating it.

The generated key is printed once. Store it as the Railway secret
``LITELLM_PROXY_VIRTUAL_KEY`` on the AncoraMind application, never in Git or a
runtime-config revision.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Mapping
from pathlib import Path

import httpx

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.domain.runtime_config.models import GATEWAY_ROUTE_PATTERN  # noqa: E402

ALIASES = ["ancoramind-default-r1", "ancoramind-fast-r1", "ancoramind-vision-r1"]

DEFAULT_KEY_RPM = 60
DEFAULT_KEY_TPM = 250_000
DEFAULT_KEY_MAX_PARALLEL_REQUESTS = 4


def resolve_aliases(env: Mapping[str, str]) -> list[str]:
    """Return the base aliases plus any explicitly requested versioned extension."""
    base = list(ALIASES)
    raw = env.get("LITELLM_VIRTUAL_KEY_ALIASES", "").strip()
    if not raw:
        return base
    extras: list[str] = []
    for candidate in raw.split(","):
        alias = candidate.strip()
        if not alias or alias in base or alias in extras:
            continue
        if not GATEWAY_ROUTE_PATTERN.fullmatch(alias):
            raise SystemExit(f"LITELLM_VIRTUAL_KEY_ALIASES entry is not a versioned alias: {alias}")
        extras.append(alias)
    return base + extras


def build_key_request_payload(env: Mapping[str, str]) -> dict[str, object]:
    """Render the /key/generate payload with per-key T12 limits (no secrets)."""
    payload: dict[str, object] = {
        "models": resolve_aliases(env),
        "metadata": {"service": "ancoramind-core"},
        "rpm_limit": _positive_int(
            env.get("LITELLM_VIRTUAL_KEY_RPM"), DEFAULT_KEY_RPM, "LITELLM_VIRTUAL_KEY_RPM"
        ),
        "tpm_limit": _positive_int(
            env.get("LITELLM_VIRTUAL_KEY_TPM"), DEFAULT_KEY_TPM, "LITELLM_VIRTUAL_KEY_TPM"
        ),
        "max_parallel_requests": _positive_int(
            env.get("LITELLM_VIRTUAL_KEY_MAX_PARALLEL_REQUESTS"),
            DEFAULT_KEY_MAX_PARALLEL_REQUESTS,
            "LITELLM_VIRTUAL_KEY_MAX_PARALLEL_REQUESTS",
        ),
    }
    max_budget = env.get("LITELLM_VIRTUAL_KEY_MAX_BUDGET_USD", "").strip()
    if max_budget:
        payload["max_budget"] = float(max_budget)
        payload["budget_duration"] = env.get("LITELLM_VIRTUAL_KEY_BUDGET_DURATION", "30d").strip()
    return payload


def _positive_int(raw: str | None, default: int, name: str) -> int:
    if raw is None or not raw.strip():
        return default
    try:
        value = int(raw.strip())
    except ValueError as exc:
        raise SystemExit(f"{name} must be a positive integer") from exc
    if value <= 0:
        raise SystemExit(f"{name} must be a positive integer")
    return value


def main() -> None:
    """Create a single key restricted to the current versioned aliases."""
    base_url = os.environ.get("LITELLM_PROXY_ADMIN_URL", "").rstrip("/")
    master_key = os.environ.get("LITELLM_MASTER_KEY", "")
    if not base_url or not master_key:
        print("LITELLM_PROXY_ADMIN_URL and LITELLM_MASTER_KEY are required", file=sys.stderr)
        raise SystemExit(2)
    response = httpx.post(
        f"{base_url}/key/generate",
        headers={"Authorization": f"Bearer {master_key}"},
        json=build_key_request_payload(os.environ),
        timeout=10.0,
    )
    response.raise_for_status()
    payload = response.json()
    key = payload.get("key")
    if not isinstance(key, str) or not key.startswith("sk-"):
        raise RuntimeError("LiteLLM key generation response did not include a valid virtual key")
    print(key)


if __name__ == "__main__":
    main()
