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

The generated key is printed once. Store it as the Railway secret
``LITELLM_PROXY_VIRTUAL_KEY`` on the AncoraMind application, never in Git or a
runtime-config revision.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Mapping

import httpx

ALIASES = ["ancoramind-default-r1", "ancoramind-fast-r1", "ancoramind-vision-r1"]

DEFAULT_KEY_RPM = 60
DEFAULT_KEY_TPM = 250_000
DEFAULT_KEY_MAX_PARALLEL_REQUESTS = 4


def build_key_request_payload(env: Mapping[str, str]) -> dict[str, object]:
    """Render the /key/generate payload with per-key T12 limits (no secrets)."""
    payload: dict[str, object] = {
        "models": list(ALIASES),
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
