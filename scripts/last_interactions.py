"""Paso 1 BL-23: consulta últimas interacciones (solo metadata, sin contenido).

Uso (PowerShell, desde la raíz del repo con el venv activado):
    python scripts/last_interactions.py
    python scripts/last_interactions.py --limit 5

Lee ANCORA_DATABASE_URL del .env y solo hace SELECT de metadata.
Nunca imprime ciphertext, payloads, textos ni secretos.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import text  # noqa: E402

from src.config import Settings  # noqa: E402
from src.repositories.database import close_database, get_session, init_database  # noqa: E402


async def _main(limit: int) -> int:
    settings = Settings()
    if not settings.ancora_database_url:
        print("Error: ANCORA_DATABASE_URL is required", file=sys.stderr)
        return 1
    init_database(settings.ancora_database_url)
    try:
        session = await get_session()
        try:
            rows = (
                await session.execute(
                    text("""
                        SELECT id, bot_id, telegram_update_id, status,
                               telegram_user_id, chat_id,
                               model_call_count, gateway_request_count,
                               tool_call_count, error_detail_code, received_at
                        FROM ancora.telegram_interactions
                        ORDER BY received_at DESC
                        LIMIT :limit
                        """),
                    {"limit": limit},
                )
            ).fetchall()
        finally:
            await session.close()
    finally:
        await close_database()
    if not rows:
        print("(sin interacciones en ancora.telegram_interactions)")
        return 0
    for row in rows:
        print(
            f"{row.received_at} update_id={row.telegram_update_id} "
            f"status={row.status} corr={row.id} "
            f"user_id={row.telegram_user_id} chat_id={row.chat_id} "
            f"model={row.model_call_count} gw={row.gateway_request_count} "
            f"tools={row.tool_call_count} err={row.error_detail_code}"
        )
    print()
    print("Ya tienes user_id/chat_id arriba: son las columnas user_id/chat_id.")
    print("Dime el update_id y te genero tmp/step1-bl23/update_<id>.json.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=10)
    args = parser.parse_args()
    return asyncio.run(_main(int(args.limit)))


if __name__ == "__main__":
    raise SystemExit(main())
