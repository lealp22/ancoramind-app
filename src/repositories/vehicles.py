"""Vehicles repository — parameterized PostgreSQL access for vehicles."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.vehicles.models import Vehicle, VehicleCreate


class VehiclesRepository:
    """Repository for vehicles in ancora schema."""

    def __init__(self, session: AsyncSession, *, auto_commit: bool = True):
        self._session = session
        self._auto_commit = auto_commit

    async def create(self, user_id: str, data: VehicleCreate) -> Vehicle:
        now = datetime.now(tz=UTC)
        stmt = text("""
            INSERT INTO ancora.vehicles
                (user_id,make,model,year,registration,nickname,vin,created_at)
            VALUES (:uid,:make,:model,:year,:reg,:nick,:vin,:now)
            RETURNING id,user_id,make,model,year,registration,nickname,vin,created_at
        """)
        r = await self._session.execute(
            stmt,
            {
                "uid": user_id,
                "make": data.make,
                "model": data.model,
                "year": data.year,
                "reg": data.registration,
                "nick": data.nickname,
                "vin": data.vin,
                "now": now,
            },
        )
        row = r.fetchone()
        if row is None:
            raise RuntimeError("Vehicle insert did not return a row")
        if self._auto_commit:
            await self._session.commit()
        return Vehicle(
            id=row.id,
            user_id=row.user_id,
            make=row.make,
            model=row.model,
            year=row.year,
            registration=row.registration,
            nickname=row.nickname,
            vin=row.vin,
            created_at=row.created_at,
        )

    async def get_by_id(self, user_id: str, vehicle_id: UUID) -> Vehicle | None:
        stmt = text("SELECT * FROM ancora.vehicles WHERE id=:id AND user_id=:uid")
        r = await self._session.execute(stmt, {"id": vehicle_id, "uid": user_id})
        row = r.fetchone()
        if not row:
            return None
        return Vehicle(
            id=row.id,
            user_id=row.user_id,
            make=row.make,
            model=row.model,
            year=row.year,
            registration=row.registration,
            nickname=row.nickname,
            vin=row.vin,
            created_at=row.created_at,
        )

    async def list_by_user(self, user_id: str) -> list[Vehicle]:
        stmt = text("SELECT * FROM ancora.vehicles WHERE user_id=:uid ORDER BY created_at DESC")
        r = await self._session.execute(stmt, {"uid": user_id})
        return [
            Vehicle(
                id=row.id,
                user_id=row.user_id,
                make=row.make,
                model=row.model,
                year=row.year,
                registration=row.registration,
                nickname=row.nickname,
                vin=row.vin,
                created_at=row.created_at,
            )
            for row in r.fetchall()
        ]

    async def find_by_reference(self, user_id: str, reference: str) -> list[Vehicle]:
        """Find vehicles matching make, model, nickname, or registration (ILIKE)."""
        pattern = f"%{reference}%"
        stmt = text("""
            SELECT * FROM ancora.vehicles
            WHERE user_id=:uid AND (
                make ILIKE :pat OR model ILIKE :pat
                OR nickname ILIKE :pat OR registration ILIKE :pat
            )
            ORDER BY created_at DESC
        """)
        r = await self._session.execute(stmt, {"uid": user_id, "pat": pattern})
        return [
            Vehicle(
                id=row.id,
                user_id=row.user_id,
                make=row.make,
                model=row.model,
                year=row.year,
                registration=row.registration,
                nickname=row.nickname,
                vin=row.vin,
                created_at=row.created_at,
            )
            for row in r.fetchall()
        ]
