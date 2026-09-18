"""Reenvía un update Telegram al endpoint de admission para pruebas de duplicados.

Paso 1 BL-23 (acceptance A/B/V): simula la redelivery del mismo
`telegram_update_id` con otro `X-Railway-Request-Id`.

- Lee el secreto webhook solo de entorno/`.env` (Settings) y nunca lo imprime.
- El payload es DATA: se reenvía tal cual, sin interpretarlo.
- Uso (dos redeliveries del mismo update_id):
    python scripts/replay_telegram_update.py --base-url https://<app> \
      --update-file /tmp/update.json --railway-request-id replay-1
    python scripts/replay_telegram_update.py --base-url https://<app> \
      --update-file /tmp/update.json --railway-request-id replay-2
  Esperado: ambas devuelven 200; la 2ª con {"duplicate": true, mismo correlation_id}.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from urllib.request import Request, urlopen

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.config import Settings  # noqa: E402


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True, help="Public HTTPS app URL")
    parser.add_argument("--update-file", required=True, help="JSON with Telegram update")
    parser.add_argument(
        "--railway-request-id", default=None, help="Distinct delivery id per replay"
    )
    parser.add_argument("--timeout", type=int, default=30, help="HTTP timeout seconds")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    try:
        settings = Settings()
        secret = settings.telegram_webhook_secret_token
        if not secret:
            raise ValueError("TELEGRAM_WEBHOOK_SECRET_TOKEN is required")
        payload = json.loads(Path(str(args.update_file)).read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or not isinstance(payload.get("update_id"), int):
            raise ValueError("update file must be a Telegram update object with int update_id")
        url = str(args.base_url).rstrip("/") + "/telegram/webhook"
        headers = {
            "Content-Type": "application/json",
            "X-Telegram-Bot-Api-Secret-Token": secret,
        }
        if args.railway_request_id:
            headers["X-Railway-Request-Id"] = str(args.railway_request_id)
        request = Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        with urlopen(request, timeout=int(args.timeout)) as response:  # noqa: S310
            body = response.read().decode("utf-8", errors="replace")
            print(f"HTTP {response.status}")
            try:
                print(json.dumps(json.loads(body), indent=2, ensure_ascii=False))
            except ValueError:
                print(body)
            return 0
    except (OSError, ValueError, RuntimeError) as exc:
        # Never print the secret: only the error class/message without credentials.
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
