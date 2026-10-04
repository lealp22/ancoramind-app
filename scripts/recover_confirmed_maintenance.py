"""Recover exactly two confirmed maintenance proposals after schema remediation.

Usage (PowerShell)::

    python scripts/recover_confirmed_maintenance.py <proposal-id-1> <proposal-id-2>

The script deliberately does not discover proposals by status. Operators must
copy the two audited IDs explicitly, preventing a broad replay after an outage.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

FAILURE_REASON = "legacy_cost_currency_ambiguous"
TOOL_NAME = "register_vehicle_maintenance"


def _database_url() -> str:
    url = os.environ.get("ANCORA_DATABASE_URL", "")
    if not url:
        raise RuntimeError("ANCORA_DATABASE_URL must be set")
    return url.replace("postgresql+asyncpg://", "postgresql://", 1)


def _parse_legacy_money(value: str | None) -> tuple[Decimal, str] | None:
    """Load the shared parser after making repository imports available."""
    # ``python scripts/...`` sets sys.path to scripts/, not the repository root.
    repository_root = Path(__file__).resolve().parents[1]
    if str(repository_root) not in sys.path:
        sys.path.insert(0, str(repository_root))
    from src.domain.vehicles.money import parse_legacy_money

    return parse_legacy_money(value)


def _money(payload: dict[str, object]) -> tuple[Decimal | None, str | None]:
    if "cost_amount" in payload:
        raw_amount = payload.get("cost_amount")
        raw_currency = payload.get("cost_currency")
        if raw_amount is None and raw_currency is None:
            return None, None
        if not isinstance(raw_amount, str) or not isinstance(raw_currency, str):
            raise ValueError("structured cost fields are invalid")
        amount = Decimal(raw_amount).quantize(Decimal("0.01"))
        currency = raw_currency.strip().upper()
        if amount < 0 or len(currency) != 3 or not currency.isalpha():
            raise ValueError("structured cost fields are invalid")
        return amount, currency
    legacy_cost = payload.get("cost")
    if legacy_cost is not None and not isinstance(legacy_cost, str):
        raise ValueError("legacy cost is invalid")
    parsed = _parse_legacy_money(legacy_cost)
    return parsed if parsed is not None else (None, None)


def _recover_one(connection: psycopg.Connection[dict[str, object]], proposal_id: UUID) -> str:
    with connection.transaction():
        proposal = connection.execute(
            """
            SELECT id, user_id, tool_name, status, payload
            FROM ancora.action_proposals
            WHERE id = %s
            FOR UPDATE
            """,
            (proposal_id,),
        ).fetchone()
        if proposal is None:
            return f"{proposal_id}: omitida (no encontrada)"
        if proposal["tool_name"] != TOOL_NAME or proposal["status"] != "confirmed":
            return f"{proposal_id}: omitida (estado/tipo no recuperable)"
        exists = connection.execute(
            "SELECT 1 FROM ancora.vehicle_maintenance WHERE source_action_id = %s",
            (proposal_id,),
        ).fetchone()
        if exists is not None:
            connection.execute(
                """
                UPDATE ancora.action_proposals
                SET status = 'executed', executed_at = now(), completed_at = now(),
                    failure_reason = NULL
                WHERE id = %s AND status = 'confirmed'
                """,
                (proposal_id,),
            )
            return f"{proposal_id}: reconciliada (mantenimiento existente)"

        payload = proposal["payload"]
        if not isinstance(payload, dict):
            raise ValueError("proposal payload is not an object")
        try:
            amount, currency = _money(payload)
        except ValueError:
            connection.execute(
                """
                UPDATE ancora.action_proposals
                SET status = 'failed_definitive', completed_at = now(), failure_reason = %s
                WHERE id = %s AND status = 'confirmed'
                """,
                (FAILURE_REASON, proposal_id),
            )
            return (
                f"{proposal_id}: fallo definitivo "
                "(importe/divisa ambiguos; crear propuesta nueva)"
            )

        vehicle_id = UUID(str(payload["vehicle_id"]))
        maintenance_date = date.fromisoformat(str(payload["date"]))
        description = str(payload["description"])
        work_performed = payload.get("work_performed", [])
        if not isinstance(work_performed, list) or not all(
            isinstance(item, str) for item in work_performed
        ):
            raise ValueError("work_performed is invalid")
        source_document_id = payload.get("source_document_id")
        connection.execute(
            """
            INSERT INTO ancora.vehicle_maintenance
                (vehicle_id, user_id, date, mileage_km, description, workshop,
                 cost_amount, cost_currency, work_performed, notes, source_document_id,
                 source_action_id)
            VALUES
                (%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s)
            """,
            (
                vehicle_id,
                proposal["user_id"],
                maintenance_date,
                payload.get("mileage_km"),
                description,
                payload.get("workshop"),
                amount,
                currency,
                json.dumps(work_performed),
                payload.get("notes"),
                UUID(str(source_document_id)) if source_document_id else None,
                proposal_id,
            ),
        )
        connection.execute(
            """
            UPDATE ancora.action_proposals
            SET status = 'executed', executed_at = now(), completed_at = now(),
                failure_reason = NULL
            WHERE id = %s AND status = 'confirmed'
            """,
            (proposal_id,),
        )
        return f"{proposal_id}: ejecutada"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("proposal_ids", nargs=2, type=UUID, metavar="PROPOSAL_ID")
    args = parser.parse_args()
    if args.proposal_ids[0] == args.proposal_ids[1]:
        parser.error("the two proposal IDs must be distinct")
    try:
        with psycopg.connect(_database_url(), row_factory=dict_row) as connection:
            for proposal_id in args.proposal_ids:
                print(_recover_one(connection, proposal_id))
    except Exception as exc:
        print(f"Recovery stopped: {type(exc).__name__}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
