"""Disposable local Gateway/auth preflight. No audio or paid inference.

Credentials live only in process/container environment, never command arguments
or output. Always destroys its dedicated project. Does NOT approve tariff.
"""

import io
import os
import secrets
import subprocess
import time
from pathlib import Path

import httpx

from src.config import Settings

ROOT = Path(__file__).resolve().parents[1]
ALIAS = "ancoramind-stt-smoke-r1"


def main() -> None:
    upstream = Settings().openrouter_api_key
    if not upstream:
        raise RuntimeError("stt_preflight_upstream_key_missing")
    env = dict(os.environ)
    env.update(
        OPENROUTER_API_KEY=upstream,
        LITELLM_MASTER_KEY="sk-" + secrets.token_hex(24),
        LITELLM_SALT_KEY=secrets.token_hex(32),
        ANCORA_SMOKE_DB_PASSWORD=secrets.token_hex(24),
    )
    command = [
        "docker",
        "compose",
        "-p",
        "ancora-stt-preflight",
        "-f",
        str(ROOT / "gateway" / "docker-compose.stt-smoke.yml"),
    ]

    def compose(*args: str) -> None:
        result = subprocess.run(
            [*command, *args], cwd=ROOT, env=env, capture_output=True, timeout=600
        )
        if result.returncode:
            raise RuntimeError("stt_preflight_compose_failed")

    try:
        compose("up", "-d")
        with httpx.Client(base_url="http://127.0.0.1:4001", timeout=10) as client:
            for _ in range(180):
                try:
                    if client.get("/health/liveliness").status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                time.sleep(1)
            else:
                raise RuntimeError("stt_preflight_start_timeout")
            response = client.post(
                "/key/generate",
                headers={"Authorization": "Bearer " + env["LITELLM_MASTER_KEY"]},
                json={"models": [ALIAS], "duration": "30m", "max_budget": 0.01},
            )
            if response.status_code != 200:
                raise RuntimeError("stt_preflight_key_generation_failed")
            key = response.json()["key"]
            models = client.get("/v1/models", headers={"Authorization": "Bearer " + key})
            if models.status_code != 200:
                raise RuntimeError("stt_preflight_key_auth_failed")
            ids = {item["id"] for item in models.json()["data"]}
            if ids != {ALIAS}:
                raise RuntimeError("stt_preflight_key_scope_invalid")
            # Nonexistent/unauthorized alias must fail before touching upstream.
            denied = client.post(
                "/v1/audio/transcriptions",
                headers={"Authorization": "Bearer " + key},
                data={"model": "not-authorized"},
                files={"file": ("synthetic.ogg", io.BytesIO(b"not-audio"), "audio/ogg")},
            )
            if denied.status_code not in {400, 401, 403}:
                raise RuntimeError("stt_preflight_alias_denial_failed")
            print(
                "PASS isolated Gateway: restricted key, one alias, "
                "unauthorized alias denied; no inference"
            )
    finally:
        compose("down", "--volumes", "--remove-orphans")


if __name__ == "__main__":
    main()
