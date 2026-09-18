"""Paso 1 BL-23: verifica evidencia en BD (metadata, sin contenido).

Uso:
    python scripts/verify_step1_evidence.py --corr-dup <uuid>
        [--corr-group <uuid>] [--corr-intruder <uuid>]

Solo SELECT de metadata. Nunca lee ciphertext ni contenido.
Verifica A/B/V (duplicados) y N/O (rechazos sin IA).
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


async def _main(corr_dup: str, corr_group: str | None,
              corr_intruder: str | None) -> int:
    settings = Settings()
    if not settings.ancora_database_url:
        print("Error: ANCORA_DATABASE_URL is required", file=sys.stderr)
        return 1
    init_database(settings.ancora_database_url)
    failures: list[str] = []
    try:
        session = await get_session()
        try:

            def check(name: str, ok: bool, detail: str) -> None:
                status = "OK" if ok else "FAIL"
                print(f"[{status}] {name}: {detail}")
                if not ok:
                    failures.append(name)

            inter = (
                await session.execute(
                    text(
                        "SELECT id, telegram_update_id, status, model_call_count,"
                        " gateway_request_count, tool_call_count, config_revision,"
                        " agno_run_id FROM ancora.telegram_interactions"
                        " WHERE id = :id"
                    ),
                    {"id": corr_dup},
                )
            ).one()
            deliveries = (
                await session.execute(
                    text(
                        "SELECT railway_request_id, duplicate, http_status,"
                        " delivery_status, received_at"
                        " FROM ancora.telegram_deliveries"
                        " WHERE interaction_id = :id ORDER BY received_at, id"
                    ),
                    {"id": corr_dup},
                )
            ).fetchall()
            llm_n = (
                await session.execute(
                    text(
                        "SELECT count(*) AS n FROM ancora.llm_usage_events"
                        " WHERE interaction_id = :id"
                    ),
                    {"id": corr_dup},
                )
            ).one().n
            resp_n = (
                await session.execute(
                    text(
                        "SELECT count(*) AS n FROM ancora.logical_responses"
                        " WHERE interaction_id = :id"
                    ),
                    {"id": corr_dup},
                )
            ).one().n
            print(
                f"dup: update_id={inter.telegram_update_id} status={inter.status}"
                f" corr={inter.id} run={inter.agno_run_id}"
                f" model={inter.model_call_count} gw={inter.gateway_request_count}"
                f" tools={inter.tool_call_count} rev={inter.config_revision}"
            )
            for d in deliveries:
                print(
                    f"  delivery: req={d.railway_request_id} dup={d.duplicate}"
                    f" http={d.http_status} st={d.delivery_status}"
                )
            print(f"  llm_usage_events={llm_n} logical_responses={resp_n}")
            check("A-una-interaccion", True, f"corr={inter.id}")
            check("B-dos-deliveries", len(deliveries) == 2,
                  f"count={len(deliveries)}")
            dup_flags = [d.duplicate for d in deliveries]
            check("B-segunda-duplicate",
                  dup_flags == [False, True], f"flags={dup_flags}")
            check("A-un-solo-run",
                  inter.model_call_count == 1 and inter.gateway_request_count == 1,
                  f"model={inter.model_call_count} gw={inter.gateway_request_count}")
            check("V-cero-IA-extra", llm_n == 1 and resp_n == 1,
                  f"llm={llm_n} resp={resp_n}")
            for label, corr in (
                ("N-grupo", corr_group),
                ("O-intruso", corr_intruder),
            ):
                if not corr:
                    continue
                row = (
                    await session.execute(
                        text(
                            "SELECT telegram_update_id, status, error_detail_code,"
                            " model_call_count, gateway_request_count,"
                            " (SELECT count(*) FROM ancora.llm_usage_events u"
                            " WHERE u.interaction_id = :id) AS llm_events"
                            " FROM ancora.telegram_interactions WHERE id = :id"
                        ),
                        {"id": corr},
                    )
                ).one()
                print(
                    f"{label}: update={row.telegram_update_id} status={row.status}"
                    f" err={row.error_detail_code} model={row.model_call_count}"
                    f" gw={row.gateway_request_count} llm={row.llm_events}"
                )
                check(f"{label}-rejected", row.status == "rejected",
                      f"status={row.status} err={row.error_detail_code}")
                zero_ia = (row.model_call_count == 0
                           and row.gateway_request_count == 0 and row.llm_events == 0)
                check(f"{label}-cero-IA", zero_ia,
                      f"model={row.model_call_count} gw={row.gateway_request_count}")
        finally:
            await session.close()
    finally:
        await close_database()
    print()
    if failures:
        print(f"FAILURES: {failures}")
        return 1
    print("Paso 1: evidencia A/B/V + N/O verificada en BD.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corr-dup", required=True)
    parser.add_argument("--corr-group", default=None)
    parser.add_argument("--corr-intruder", default=None)
    args = parser.parse_args()
    return asyncio.run(
        _main(
            str(args.corr_dup),
            str(args.corr_group) if args.corr_group else None,
            str(args.corr_intruder) if args.corr_intruder else None,
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
