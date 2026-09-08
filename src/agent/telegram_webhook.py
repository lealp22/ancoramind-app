"""Telegram webhook API helpers used by deployment scripts.

This module belongs to the infrastructure layer. It never logs bot tokens or
webhook secret tokens.
"""

import json
from collections.abc import Callable, Mapping
from typing import Any
from urllib.error import URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen


def build_webhook_url(base_url: str) -> str:
    """Build the canonical AncoraMind Telegram webhook URL from a public HTTPS URL."""
    normalized = base_url.rstrip("/")
    parsed = urlparse(normalized)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ValueError("Webhook base URL must be a public HTTPS URL")
    if parsed.query or parsed.fragment:
        raise ValueError("Webhook base URL must not contain query parameters or fragments")
    return f"{normalized}/telegram/webhook"


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
