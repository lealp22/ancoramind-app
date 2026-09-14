"""Create one AncoraMind-only LiteLLM virtual key after the T11 proxy is healthy.

Usage (PowerShell):
  $env:LITELLM_PROXY_ADMIN_URL='http://localhost:4000'
  $env:LITELLM_MASTER_KEY='sk-...'
  python scripts/litellm_create_virtual_key.py

The generated key is printed once. Store it as the Railway secret
``LITELLM_PROXY_VIRTUAL_KEY`` on the AncoraMind application, never in Git or a
runtime-config revision.
"""

from __future__ import annotations

import os
import sys

import httpx

ALIASES = ["ancoramind-default-r1", "ancoramind-fast-r1", "ancoramind-vision-r1"]


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
        json={"models": ALIASES, "metadata": {"service": "ancoramind-core"}},
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
