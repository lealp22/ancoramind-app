"""Manage the protected runtime-config control plane without exposing secrets.

The admin bearer token comes from Settings/environment only and is never
printed, logged or persisted. Example:

    $env:RUNTIME_CONFIG_ADMIN_TOKEN = '<token>'
    python scripts/runtime_config.py status --base-url https://example.com
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any
from urllib import request as urllib_request
from urllib.error import HTTPError, URLError

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.config import Settings  # noqa: E402


def _settings() -> Settings:
    settings = Settings()
    if not settings.runtime_config_admin_enabled:
        raise ValueError("RUNTIME_CONFIG_ADMIN_ENABLED must be true")
    return settings


def _admin_token(settings: Settings) -> str:
    token = os.environ.get("RUNTIME_CONFIG_ADMIN_TOKEN") or settings.runtime_config_admin_token
    if not token:
        raise ValueError("RUNTIME_CONFIG_ADMIN_TOKEN is required")
    return token


def _admin_actor() -> str:
    actor = os.environ.get("RUNTIME_CONFIG_ADMIN_ACTOR", "").strip()
    if not actor:
        raise ValueError("RUNTIME_CONFIG_ADMIN_ACTOR is required")
    return actor


def _load_json_file(path: str) -> dict[str, Any]:
    try:
        with Path(path).open(encoding="utf-8") as handle:
            loaded = json.load(handle)
    except (OSError, ValueError) as exc:
        raise ValueError(f"Cannot read JSON config file {path!r}") from exc
    if not isinstance(loaded, dict):
        raise ValueError(f"JSON config file {path!r} must contain an object")
    return loaded


def _request(
    *,
    base_url: str,
    method: str,
    path: str,
    token: str,
    actor: str,
    payload: dict[str, Any] | None = None,
) -> tuple[int, str]:
    body = json.dumps(payload or {}).encode("utf-8") if payload else None
    http_request = urllib_request.Request(
        base_url.rstrip("/") + path,
        data=body,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "X-Ancora-Admin-Actor": actor,
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib_request.urlopen(http_request, timeout=30) as response:  # noqa: S310
            return response.status, response.read().decode("utf-8", errors="replace")
    except HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", errors="replace")
    except URLError as exc:
        raise RuntimeError(f"Runtime config admin request failed: {exc}") from exc


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True, help="Public HTTPS app URL")
    subcommands = parser.add_subparsers(dest="command", required=True)

    subcommands.add_parser("status", help="Show active runtime-config metadata")
    validate_parser = subcommands.add_parser("validate", help="Validate a config file")
    validate_parser.add_argument("--config", required=True, help="JSON runtime config file")

    create_parser = subcommands.add_parser("create-revision", help="Create a valid revision")
    create_parser.add_argument("--config", required=True, help="JSON runtime config file")
    create_parser.add_argument("--reason", required=True, help="Audit reason")

    activate_parser = subcommands.add_parser("activate", help="CAS-activate a revision")
    activate_parser.add_argument("--revision", required=True, type=int)
    activate_parser.add_argument("--expected-current-revision", required=True, type=int)
    activate_parser.add_argument("--reason", required=True, help="Audit reason")

    rollback_parser = subcommands.add_parser("rollback", help="Restore an older revision")
    rollback_parser.add_argument("--revision", required=True, type=int)
    rollback_parser.add_argument("--expected-current-revision", required=True, type=int)
    rollback_parser.add_argument("--reason", required=True, help="Audit reason")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    try:
        settings = _settings()
        token = _admin_token(settings)
        actor = _admin_actor()
        command = str(args.command)

        if command == "status":
            status_code, text = _request(
                base_url=args.base_url,
                method="GET",
                path="/admin/runtime-config/status",
                token=token,
                actor=actor,
            )
        elif command == "validate":
            status_code, text = _request(
                base_url=args.base_url,
                method="POST",
                path="/admin/runtime-config/validate",
                token=token,
                actor=actor,
                payload={"config": _load_json_file(str(args.config))},
            )
        elif command == "create-revision":
            status_code, text = _request(
                base_url=args.base_url,
                method="POST",
                path="/admin/runtime-config/revisions",
                token=token,
                actor=actor,
                payload={
                    "config": _load_json_file(str(args.config)),
                    "reason": str(args.reason),
                },
            )
        elif command == "activate":
            status_code, text = _request(
                base_url=args.base_url,
                method="POST",
                path=f"/admin/runtime-config/revisions/{int(args.revision)}/activate",
                token=token,
                actor=actor,
                payload={
                    "expected_current_revision": int(args.expected_current_revision),
                    "reason": str(args.reason),
                },
            )
        else:
            status_code, text = _request(
                base_url=args.base_url,
                method="POST",
                path="/admin/runtime-config/rollback",
                token=token,
                actor=actor,
                payload={
                    "revision": int(args.revision),
                    "expected_current_revision": int(args.expected_current_revision),
                    "reason": str(args.reason),
                },
            )
        print(f"HTTP {status_code}")
        try:
            print(json.dumps(json.loads(text or "{}"), indent=2, ensure_ascii=False))
        except ValueError:
            print(text)
        return 0 if 200 <= status_code < 300 else 1
    except (RuntimeError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
