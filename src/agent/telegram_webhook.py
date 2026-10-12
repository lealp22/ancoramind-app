"""Telegram webhook API helpers used by deployment scripts.

This module belongs to the infrastructure layer. It never logs bot tokens or
webhook secret tokens.
"""

import json
from collections.abc import Callable, Mapping, Sequence
from typing import Any
from urllib.error import URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

TELEGRAM_WEBHOOK_ALLOWED_UPDATES = ("message", "callback_query")
"""Inbound updates required by the governed Telegram admission pipeline."""


def build_webhook_url(base_url: str) -> str:
    """Build the canonical AncoraMind Telegram webhook URL from a public HTTPS URL."""
    normalized = base_url.rstrip("/")
    parsed = urlparse(normalized)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ValueError("Webhook base URL must be a public HTTPS URL")
    if parsed.query or parsed.fragment:
        raise ValueError("Webhook base URL must not contain query parameters or fragments")
    return f"{normalized}/telegram/webhook"


def build_webhook_registration_payload(webhook_url: str, secret_token: str) -> dict[str, str]:
    """Build the secret-bearing Bot API payload without omitting consent callbacks."""
    return {
        "url": webhook_url,
        "secret_token": secret_token,
        "allowed_updates": json.dumps(TELEGRAM_WEBHOOK_ALLOWED_UPDATES),
    }


def telegram_api_request(
    token: str,
    method: str,
    payload: Mapping[str, str] | None = None,
    *,
    opener: Callable[..., Any] = urlopen,
) -> dict[str, Any]:
    """Call Telegram's Bot API without exposing credentials in raised errors."""
    request = Request(
        url=f"https://api.telegram.org/bot{token}/{method}",
        data=urlencode(payload or {}).encode("utf-8"),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with opener(request, timeout=15) as response:
            raw_response = response.read()
    except URLError as exc:
        raise RuntimeError(f"Telegram API request failed: {exc.reason}") from exc

    try:
        body = json.loads(raw_response)
    except (TypeError, json.JSONDecodeError) as exc:
        raise RuntimeError("Telegram API returned an invalid JSON response") from exc

    if not body.get("ok"):
        raise RuntimeError(body.get("description", "Telegram API rejected the request"))
    result = body.get("result", {})
    return result if isinstance(result, dict) else {"result": result}


def summarize_webhook_info(info: Mapping[str, Any]) -> dict[str, Any]:
    """Return non-secret webhook status fields suitable for terminal output."""
    fields = (
        "url",
        "has_custom_certificate",
        "pending_update_count",
        "last_error_date",
        "last_error_message",
        "max_connections",
    )
    return {field: info[field] for field in fields if field in info}


def build_command_menu_payload(commands: Sequence[tuple[str, str]]) -> str:
    """Serialize the Bot API ``setMyCommands`` menu from name/description pairs.

    ``commands`` comes from the domain map of handled commands, so the Telegram
    autocomplete menu can never advertise something the processor refuses. The
    Bot API limits are validated here to fail loudly at registration time.
    """
    if not commands:
        raise ValueError("Telegram command menu must not be empty")
    for name, description in commands:
        if not name.isascii() or not name.replace("_", "").isalnum():
            raise ValueError(f"Invalid Telegram command name: {name!r}")
        if not description.strip() or len(description) > 256:
            raise ValueError(f"Invalid Telegram command description for {name!r}")
    return json.dumps(
        [{"command": name, "description": description} for name, description in commands],
        ensure_ascii=False,
    )
