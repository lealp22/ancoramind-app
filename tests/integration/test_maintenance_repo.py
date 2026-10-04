"""Integration tests for MaintenanceRepository against real PostgreSQL (specs/009)."""

from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from src.domain.vehicles.models import VehicleCreate, VehicleMaintenanceCreate
from src.repositories.maintenance import MaintenanceRepository
from src.repositories.vehicles import VehiclesRepository

pytestmark = pytest.mark.integration


async def test_history_last_and_jsonb_roundtrip(session, user_a, user_b):
    vehicles = VehiclesRepository(session)
    repo = MaintenanceRepository(session)

    v = await vehicles.create(user_a, VehicleCreate(make="Seat", model="Ibiza"))

    m1 = await repo.create(
        user_a,
        VehicleMaintenanceCreate(
            vehicle_id=v.id,
            date=date(2026, 1, 10),
            mileage_km=95000,
            description="Cambio de aceite",
            workshop="Taller Ruiz",
            cost_amount=Decimal("180.00"),
            cost_currency="EUR",
            work_performed=["aceite", "filtro"],
        ),
    )
    # JSONB round-trip preserves the list
    assert m1.work_performed == ["aceite", "filtro"]
    assert m1.cost_amount == Decimal("180.00")
    assert m1.cost_currency == "EUR"

    await repo.create(
        user_a,
        VehicleMaintenanceCreate(
            vehicle_id=v.id,
            date=date(2026, 7, 20),
            description="Revisión anual",
            work_performed=[],
        ),
    )

    history = await repo.get_history(user_a, v.id)
    assert [h.date for h in history] == [date(2026, 7, 20), date(2026, 1, 10)]

    last = await repo.get_last(user_a, v.id)
    assert last is not None
    assert last.description == "Revisión anual"
    assert last.created_at.tzinfo is not None

    # User scoping: user B sees nothing even with a valid vehicle id
    assert await repo.get_history(user_b, v.id) == []
    assert await repo.get_last(user_b, v.id) is None


async def test_source_action_id_is_idempotent(session, user_a):
    vehicles = VehiclesRepository(session)
    repo = MaintenanceRepository(session)
    v = await vehicles.create(user_a, VehicleCreate(make="Seat", model="Ibiza"))
    proposal_id = uuid4()
    await session.execute(
        text("""
            INSERT INTO ancora.action_proposals (id, user_id, tool_name, status, payload)
            VALUES (:id, :user_id, 'register_vehicle_maintenance', 'executed', '{}'::jsonb)
        """),
        {"id": proposal_id, "user_id": user_a},
    )
    await session.commit()
    data = VehicleMaintenanceCreate(
        vehicle_id=v.id,
        date=date(2026, 1, 10),
        description="Cambio de aceite",
        source_action_id=proposal_id,
    )
    await repo.create(user_a, data)
    with pytest.raises(IntegrityError):
        await repo.create(user_a, data)
    await session.rollback()


async def test_fk_requires_existing_vehicle(session, user_a):
    repo = MaintenanceRepository(session)

    with pytest.raises(IntegrityError):
        await repo.create(
            user_a,
            VehicleMaintenanceCreate(
                vehicle_id=uuid4(),
                date=date(2026, 1, 1),
                description="mantenimiento fantasma",
            ),
        )
    await session.rollback()


async def test_cascade_delete_vehicle_removes_maintenance(session, user_a):
    vehicles = VehiclesRepository(session)
    repo = MaintenanceRepository(session)

    v = await vehicles.create(user_a, VehicleCreate(make="Ford", model="Focus"))
    await repo.create(
        user_a,
        VehicleMaintenanceCreate(
            vehicle_id=v.id, date=date(2026, 2, 1), description="Frenos"
        ),
    )

    # VehiclesRepository has no delete tool (WRITE/DESTRUCTIVE governance);
    # parameterized raw SQL is acceptable as test scaffolding.
    await session.execute(
        text("DELETE FROM ancora.vehicles WHERE id = :id"), {"id": v.id}
    )
    await session.commit()

    assert await repo.get_history(user_a, v.id) == []
