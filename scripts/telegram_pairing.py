"""Operate governed Telegram pairing through the protected HTTPS admin API.

The bearer token is read from Settings/environment and is never printed, logged
or persisted. Mutating commands require RUNTIME_CONFIG_ADMIN_ACTOR so each
authorization decision remains durable and auditable. Run from the repository
root, for example:

    $env:RUNTIME_CONFIG_ADMIN_ACTOR = 'operator@example.com'
    python scripts/telegram_pairing.py list-pending --base-url https://example.com
    python scripts/telegram_pairing.py issue --base-url https://example.com `
        --reason 'controlled evaluator' --expires-in-minutes 60

``issue`` prints the one-time invitation code returned by the API. Share it only
through an approved private channel; do not copy it into tickets, logs or chat.
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
    if not settings.telegram_pairing_admin_enabled:
        raise ValueError("TELEGRAM_PAIRING_ADMIN_ENABLED must be true")
    return settings


def _admin_token(settings: Settings) -> str:
    token = os.environ.get("RUNTIME_CONFIG_ADMIN_TOKEN") or settings.runtime_config_admin_token
    if not token:
        raise ValueError("RUNTIME_CONFIG_ADMIN_TOKEN is required")
    return token


def _admin_actor() -> str:
    actor = os.environ.get("RUNTIME_CONFIG_ADMIN_ACTOR", "").strip()
    if not actor:
        raise ValueError("RUNTIME_CONFIG_ADMIN_ACTOR is required for a pairing mutation")
    return actor


def _request(
    *,
    base_url: str,
    method: str,
    path: str,
    token: str,
    actor: str | None = None,
    payload: dict[str, Any] | None = None,
) -> tuple[int, str]:
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    if actor is not None:
        headers["X-Ancora-Admin-Actor"] = actor
    http_request = urllib_request.Request(
        base_url.rstrip("/") + path,
        data=body,
        method=method,
        headers=headers,
    )
    try:
        with urllib_request.urlopen(http_request, timeout=30) as response:  # noqa: S310
            return response.status, response.read().decode("utf-8", errors="replace")
    except HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", errors="replace")
    except URLError as exc:
        raise RuntimeError(f"Telegram pairing admin request failed: {exc}") from exc


def build_operation(args: argparse.Namespace) -> tuple[str, str, dict[str, Any] | None, bool]:
    """Return method, path, JSON body and whether the operation mutates state."""
    command = str(args.command)
    if command == "list-pending":
        return "GET", f"/admin/telegram-pairing/requests?limit={int(args.limit)}", None, False
    if command == "issue":
        return (
            "POST",
            "/admin/telegram-pairing/invitations",
            {
                "max_uses": int(args.max_uses),
                "expires_in_minutes": int(args.expires_in_minutes),
                "reason": str(args.reason),
            },
            True,
        )
    if command in {"approve", "reject"}:
        return (
            "POST",
            f"/admin/telegram-pairing/requests/{args.request_id}/{command}",
            {"reason": str(args.reason)},
            True,
        )
    if command == "revoke-invitation":
        return (
            "POST",
            f"/admin/telegram-pairing/invitations/{args.invitation_id}/revoke",
            {"reason": str(args.reason)},
            True,
        )
    if command == "revoke-authorization":
        return (
            "POST",
            f"/admin/telegram-pairing/authorizations/{int(args.telegram_user_id)}/revoke",
            {"reason": str(args.reason)},
            True,
        )
    raise ValueError(f"Unsupported pairing command: {command}")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True, help="Public HTTPS app URL")
    subcommands = parser.add_subparsers(dest="command", required=True)

    list_parser = subcommands.add_parser(
        "list-pending", help="List bounded pending pairing requests"
    )
    list_parser.add_argument("--limit", type=int, default=100, choices=range(1, 101))

    issue_parser = subcommands.add_parser("issue", help="Issue a one-time-display invitation code")
    issue_parser.add_argument("--max-uses", type=int, default=1, choices=range(1, 101))
    issue_parser.add_argument("--expires-in-minutes", type=int, default=60, choices=range(5, 10081))
    issue_parser.add_argument("--reason", required=True, help="Auditable issuance reason")

    for command, help_text in (
        ("approve", "Approve a pending pairing request"),
        ("reject", "Reject a pending pairing request"),
    ):
        decision_parser = subcommands.add_parser(command, help=help_text)
        decision_parser.add_argument("--request-id", required=True, help="Pairing request UUID")
        decision_parser.add_argument("--reason", required=True, help="Auditable decision reason")

    invitation_parser = subcommands.add_parser(
        "revoke-invitation", help="Immediately prevent further invitation redemption"
    )
    invitation_parser.add_argument("--invitation-id", required=True, help="Pairing invitation UUID")
    invitation_parser.add_argument("--reason", required=True, help="Auditable revocation reason")

    authorization_parser = subcommands.add_parser(
        "revoke-authorization", help="Immediately block future private admissions for a user"
    )
    authorization_parser.add_argument("--telegram-user-id", required=True, type=int)
    authorization_parser.add_argument("--reason", required=True, help="Auditable revocation reason")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    try:
        settings = _settings()
        method, path, payload, mutates = build_operation(args)
        status_code, text = _request(
            base_url=str(args.base_url),
            method=method,
            path=path,
            token=_admin_token(settings),
            actor=_admin_actor() if mutates else None,
            payload=payload,
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
