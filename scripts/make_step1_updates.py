"""Genera update.json sintéticos para el paso 1 BL-23 (duplicados A/B/V).

Uso:
    python scripts/make_step1_updates.py
    python scripts/make_step1_updates.py --user-id 452022640 --chat-id 452022640

Genera en tmp/step1-bl23/:
- update_dup.json: update NUEVO (update_id alto, nunca usado) para el test
  de duplicados. Se envía DOS veces con distinto X-Railway-Request-Id.
- update_group.json: update de grupo (debe ser rejected non_private_chat).
- update_unknown_user.json: usuario fuera de allowlist (rejected user_not_allowlisted).

El user_id/chat_id por defecto salen de la última interacción real de la BD
(solo metadata, sin contenido). Todo se ejecuta en local; el envío a Railway
es el paso siguiente con replay_telegram_update.py.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import text  # noqa: E402

from src.config import Settings  # noqa: E402
from src.repositories.database import close_database, get_session, init_database  # noqa: E402

OUT_DIR = PROJECT_ROOT / "tmp" / "step1-bl23"


async def _discover_ids() -> tuple[int, int, int]:
    """Devuelve (max_update_id, user_id, chat_id) desde la BD local."""
    settings = Settings()
    if not settings.ancora_database_url:
        raise ValueError("ANCORA_DATABASE_URL is required")
    init_database(settings.ancora_database_url)
    try:
        session = await get_session()
        try:
            row = (
                await session.execute(
                    text("""
                        SELECT max(telegram_update_id) AS max_update,
                               max(telegram_user_id) AS user_id,
                               max(chat_id) AS chat_id
                        FROM ancora.telegram_interactions
                        """)
                )
            ).one()
        finally:
            await session.close()
    finally:
        await close_database()
    return int(row.max_update or 978198899), int(row.user_id or 0), int(row.chat_id or 0)


def _private_update(update_id: int, user_id: int, chat_id: int, text: str) -> dict:
    return {
        "update_id": update_id,
        "message": {
            "message_id": update_id % 100000,
            "from": {"id": user_id, "is_bot": False, "first_name": "Paso1"},
            "chat": {"id": chat_id, "type": "private"},
            "date": 1790000000,
            "text": text,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--user-id", type=int, default=None)
    parser.add_argument("--chat-id", type=int, default=None)
    args = parser.parse_args()

    if args.user_id and args.chat_id:
        max_update, user_id, chat_id = 978198899, int(args.user_id), int(args.chat_id)
    else:
        max_update, user_id, chat_id = asyncio.run(_discover_ids())
    if not user_id or not chat_id:
        print("Error: no se pudo descubrir user_id/chat_id de la BD", file=sys.stderr)
        return 1

    new_id = max_update + 1000  # hueco amplio para no colisionar con Telegram real
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    files = {
        "update_dup.json": _private_update(new_id, user_id, chat_id, "ping paso 1"),
        "update_group.json": {
            "update_id": new_id + 1,
            "message": {
                "message_id": (new_id + 1) % 100000,
                "from": {"id": user_id, "is_bot": False, "first_name": "Paso1"},
                "chat": {"id": -1001234567890, "type": "group"},
                "date": 1790000000,
                "text": "hola desde grupo",
            },
        },
        "update_unknown_user.json": _private_update(
            new_id + 2, 999999999, 999999999, "soy un intruso"
        ),
    }
    for name, payload in files.items():
        path = OUT_DIR / name
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"OK {path} (update_id={payload['update_id']})")
    print()
    print(f"user_id={user_id} chat_id={chat_id} base_update_id={new_id}")
    print("Siguiente: enviar update_dup.json DOS veces a Railway (ver abajo).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
