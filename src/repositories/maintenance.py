"""Vehicle maintenance repository — parameterized SQL."""

import json
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import Row, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.vehicles.models import VehicleMaintenance, VehicleMaintenanceCreate


class MaintenanceRepository:
    """Repository for vehicle maintenance records."""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def create(
        self, user_id: str, data: VehicleMaintenanceCreate, *, commit: bool = True
    ) -> VehicleMaintenance:
        now = datetime.now(tz=UTC)
        stmt = text("""
            INSERT INTO ancora.vehicle_maintenance
                (vehicle_id,user_id,date,mileage_km,description,workshop,cost_amount,cost_currency,
                 work_performed,notes,source_document_id,source_action_id,created_at)
            VALUES (:vid,:uid,:date,:mileage,:desc,:ws,:cost_amount,:cost_currency,
                    CAST(:wp AS jsonb),:notes,:src,:source_action_id,:now)
            RETURNING *
        """)
        r = await self._session.execute(stmt, {
            "vid": data.vehicle_id, "uid": user_id, "date": data.date,
            "mileage": data.mileage_km, "desc": data.description, "ws": data.workshop,
            "cost_amount": data.cost_amount, "cost_currency": data.cost_currency,
            "wp": json.dumps(data.work_performed), "notes": data.notes,
            "src": data.source_document_id, "source_action_id": data.source_action_id, "now": now,
        })
        row = r.fetchone()
        if row is None:
            raise RuntimeError("Vehicle maintenance insert did not return a row")
        if commit:
            await self._session.commit()
        return VehicleMaintenance(
            id=row.id, vehicle_id=row.vehicle_id, user_id=row.user_id,
            date=row.date, mileage_km=row.mileage_km, description=row.description,
            workshop=row.workshop, cost_amount=row.cost_amount, cost_currency=row.cost_currency,
            work_performed=row.work_performed, notes=row.notes,
            source_document_id=row.source_document_id, source_action_id=row.source_action_id,
            created_at=row.created_at,
        )

    async def get_history(self, user_id: str, vehicle_id: UUID) -> list[VehicleMaintenance]:
        stmt = text("""
            SELECT * FROM ancora.vehicle_maintenance
            WHERE vehicle_id=:vid AND user_id=:uid ORDER BY date DESC, created_at DESC
        """)
        r = await self._session.execute(stmt, {"vid": vehicle_id, "uid": user_id})
        return [_row_to_maintenance(row) for row in r.fetchall()]

    async def get_last(self, user_id: str, vehicle_id: UUID) -> VehicleMaintenance | None:
        stmt = text("""
            SELECT * FROM ancora.vehicle_maintenance
            WHERE vehicle_id=:vid AND user_id=:uid ORDER BY date DESC LIMIT 1
        """)
        r = await self._session.execute(stmt, {"vid": vehicle_id, "uid": user_id})
        row = r.fetchone()
        return _row_to_maintenance(row) if row else None


def _row_to_maintenance(row: Row[tuple[object, ...]]) -> VehicleMaintenance:
    return VehicleMaintenance(
        id=row.id, vehicle_id=row.vehicle_id, user_id=row.user_id,
        date=row.date, mileage_km=row.mileage_km, description=row.description,
        workshop=row.workshop, cost_amount=row.cost_amount, cost_currency=row.cost_currency,
        work_performed=row.work_performed or [], notes=row.notes,
        source_document_id=row.source_document_id, source_action_id=row.source_action_id,
        created_at=row.created_at,
    )
