"""Register, inspect, or delete AncoraMind's stable Telegram webhook.

The script obtains TELEGRAM_TOKEN and TELEGRAM_WEBHOOK_SECRET_TOKEN from the
environment or the repository .env through Settings. It never prints either
secret. Run it from the repository root, for example:

    python scripts/telegram_webhook.py set --base-url https://example.up.railway.app
    python scripts/telegram_webhook.py commands

``commands`` publishes the bot autocomplete menu from the domain map in
``src/domain/interactions/commands.py`` (the same map the processor executes).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.agent.telegram_webhook import (  # noqa: E402
    build_command_menu_payload,
    build_webhook_url,
    summarize_webhook_info,
    telegram_api_request,
)
from src.config import Settings  # noqa: E402
from src.domain.interactions.commands import BOT_COMMAND_MENU  # noqa: E402


def _settings() -> Settings:
    settings = Settings()
    if not settings.telegram_token:
        raise ValueError("TELEGRAM_TOKEN is required")
    return settings


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subcommands = parser.add_subparsers(dest="command", required=True)

    set_parser = subcommands.add_parser("set", help="Register the Railway webhook")
    set_parser.add_argument("--base-url", required=True, help="Public HTTPS Railway service URL")

    subcommands.add_parser("status", help="Show sanitized Telegram webhook status")

    subcommands.add_parser(
        "commands",
        help="Register the bot command menu (autocomplete) from the domain map",
    )

    delete_parser = subcommands.add_parser("delete", help="Delete the active Telegram webhook")
    delete_parser.add_argument(
        "--drop-pending-updates",
        action="store_true",
        help="Discard queued Telegram updates while deleting the webhook",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    try:
        settings = _settings()
        if args.command == "set":
            if not settings.telegram_webhook_secret_token:
                raise ValueError("TELEGRAM_WEBHOOK_SECRET_TOKEN is required to register a webhook")
            webhook_url = build_webhook_url(args.base_url)
            telegram_api_request(
                settings.telegram_token,
                "setWebhook",
                {
                    "url": webhook_url,
                    "secret_token": settings.telegram_webhook_secret_token,
                    "allowed_updates": json.dumps(["message"]),
                },
            )
            print(f"Webhook registered: {webhook_url}")
            return 0

        if args.command == "status":
            info = telegram_api_request(settings.telegram_token, "getWebhookInfo")
            print(json.dumps(summarize_webhook_info(info), indent=2, ensure_ascii=False))
            return 0

        if args.command == "commands":
            payload = build_command_menu_payload(BOT_COMMAND_MENU)
            telegram_api_request(settings.telegram_token, "setMyCommands", {"commands": payload})
            registered = ", ".join(f"/{name}" for name, _ in BOT_COMMAND_MENU)
            print(f"Command menu registered: {registered}")
            return 0

        telegram_api_request(
            settings.telegram_token,
            "deleteWebhook",
            {"drop_pending_updates": str(args.drop_pending_updates).lower()},
        )
        print("Webhook deleted.")
        return 0
    except (RuntimeError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
