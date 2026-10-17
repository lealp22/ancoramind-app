"""Operator-only: run in the existing LiteLLM shell, never the eval container.

Uses the Gateway's existing environment and loopback only. Creates ONE expiring,
read-only eval key; never enables inference. The secret is delivered exclusively
to /dev/tty, never stdout/stderr, files, argv or reports. Do not pipe/record the TTY.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
from collections.abc import Callable, Mapping
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any, TextIO
from urllib.error import HTTPError
from urllib.request import ProxyHandler, Request, build_opener

ALIAS = "ancoramind-default-r4"
READ_ROUTES = ["/models", "/v1/models", "/key/info"]


class ProvisionError(ValueError):
    """Fixed errors only, with no HTTP body or secret-bearing diagnostics."""


def empty_json_object(value: object) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        value = json.loads(value)
    return isinstance(value, dict) and not value


def request_local(
    base: str, method: str, route: str, token: str, payload: dict | None,
) -> dict:
    """No proxies, redirects, automatic retry or inference endpoint."""
    if (
        not re.fullmatch(r"http://127\.0\.0\.1:[0-9]{1,5}", base)
        or (method, route) not in {
            ("GET", "/v1/models"), ("POST", "/key/generate"),
            ("GET", "/key/info"), ("POST", "/key/delete"),
        }
    ):
        raise ProvisionError("eval_key_route_forbidden")
    data = None if payload is None else json.dumps(payload).encode()
    request = Request(base + route, data=data, method=method, headers={
        "Authorization": "Bearer " + token, "Content-Type": "application/json",
    })
    # Never follow a redirect with credentials, even on the local management API.
    from urllib.request import HTTPRedirectHandler

    class NoRedirect(HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None

    try:
        with build_opener(ProxyHandler({}), NoRedirect()).open(request, timeout=15) as response:
            result = json.load(response)
        if not isinstance(result, dict):
            raise ProvisionError("eval_key_invalid_response")
        return result
    except HTTPError:
        raise ProvisionError("eval_key_http_failed") from None


def provision(
    env: Mapping[str, str], call: Callable[..., dict], deliver: Callable[[str], None],
    now: datetime, key_alias: str,
) -> dict[str, Any]:
    """Verify persisted restrictions before handing off a secret. Never retry creation."""
    port = env.get("PORT", "4000")
    master = env.get("LITELLM_MASTER_KEY", "").strip()
    if not master or not re.fullmatch(r"[0-9]{1,5}", port) or not 1 <= int(port) <= 65535:
        raise ProvisionError("eval_gateway_shell_required")
    base = "http://127.0.0.1:" + port
    models = call(base, "GET", "/v1/models", master, None)
    if ALIAS not in {m.get("id") for m in models.get("data", []) if isinstance(m, dict)}:
        raise ProvisionError("eval_alias_missing")
    payload = {
        "key_alias": key_alias, "models": [ALIAS], "duration": "2h",
        "key_type": "default", "allowed_routes": READ_ROUTES,
        "max_budget": 0.10, "budget_duration": None, "spend": 0,
        "max_parallel_requests": 1, "rpm_limit": 30, "tpm_limit": 250000,
        "auto_rotate": False, "send_invite_email": False,
        "metadata": {"service": "ancoramind-evals", "purpose": "t7-access-only"},
    }
    created = call(base, "POST", "/key/generate", master, payload)
    key = created.get("key")
    if not isinstance(key, str) or not key.startswith("sk-"):
        raise ProvisionError("eval_key_creation_ambiguous_do_not_repeat")
    try:
        info = call(base, "GET", "/key/info", key, None).get("info", {})
        expires = datetime.fromisoformat(info["expires"].replace("Z", "+00:00"))
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=UTC)
        if (
            info.get("key_alias") != key_alias
            or info.get("models") != [ALIAS]
            or set(info.get("allowed_routes") or []) != set(READ_ROUTES)
            or Decimal(str(info.get("max_budget"))) != Decimal("0.10")
            or Decimal(str(info.get("spend"))) != 0
            or info.get("budget_duration") is not None
            or info.get("budget_reset_at") is not None
            or info.get("max_parallel_requests") != 1
            or info.get("rpm_limit") != 30 or info.get("tpm_limit") != 250000
            or not now < expires <= now + timedelta(hours=2, minutes=2)
            or info.get("blocked") or info.get("auto_rotate")
            or any(not empty_json_object(info.get(field))
                   for field in ("aliases", "config", "permissions"))
        ):
            raise ProvisionError("eval_key_restrictions_mismatch")
        visible = call(base, "GET", "/v1/models", key, None).get("data", [])
        if not visible or {m.get("id") for m in visible} != {ALIAS}:
            raise ProvisionError("eval_key_scope_mismatch")
        deliver(key)
        return {
            "status": "eval_key_read_only_ready", "key_alias": key_alias,
            "models": [ALIAS], "expires": expires.isoformat(),
            "max_budget_usd": "0.10", "budget_reset": False, "spend_usd": "0",
            "max_parallel_requests": 1, "rpm_limit": 30, "tpm_limit": 250000,
            "gateway_port": int(port),
            "allowed_routes": READ_ROUTES, "inference_enabled": False,
            "inference_started": False, "campaign_approval": "pending",
            "pricing_verified": False,
        }
    except BaseException:
        # Only remove the just-created key, never any existing bot/provider key.
        try:
            deleted = call(base, "POST", "/key/delete", master, {"keys": [key]})
            if (
                deleted.get("failed_tokens")
                or not set(deleted.get("deleted_keys") or [])
                & {key, hashlib.sha256(key.encode()).hexdigest()}
            ):
                raise ProvisionError("eval_key_cleanup_unknown_do_not_repeat")
        except Exception:
            raise ProvisionError("eval_key_cleanup_unknown_do_not_repeat") from None
        raise ProvisionError("eval_key_verification_failed_created_key_revoked") from None


def deliver_console(console: TextIO, key: str) -> None:
    console.write("\nCLAVE EVAL TEMPORAL — guardar en gestor de secretos, NO pegar en chat/logs:\n")
    console.write(key + "\n")
    console.flush()


def main() -> int:
    alias = "ancoramind-evals-access-" + uuid.uuid4().hex[:12]
    try:
        # Open BEFORE creating anything: no headless key with nowhere safe to deliver it.
        with open("/dev/tty", "w", encoding="utf-8") as console:
            if not console.isatty():
                raise ProvisionError("eval_private_tty_required")
            report = provision(
                os.environ, request_local, lambda key: deliver_console(console, key),
                datetime.now(UTC), alias,
            )
        print(json.dumps(report))
        return 0
    except (Exception, KeyboardInterrupt) as error:
        print(json.dumps({"status": "eval_key_blocked_or_ambiguous", "key_alias": alias,
                          "code": str(error) if isinstance(error, ProvisionError)
                          else "eval_key_operator_inspection_required",
                          "inference_started": False, "do_not_repeat_creation": True}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
