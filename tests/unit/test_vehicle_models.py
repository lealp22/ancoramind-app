"""Unit tests for Vehicle domain models."""

from datetime import date, datetime, timezone
from uuid import uuid4

from src.domain.vehicles.models import (
    Vehicle,
    VehicleCreate,
    VehicleMaintenance,
    VehicleMaintenanceCreate,
    VehicleResolution,
    VehicleSummary,
)


class TestVehicleCreate:
    def test_minimal(self):
        vc = VehicleCreate(make="Ford", model="Mondeo")
        assert vc.make == "Ford"
        assert vc.model == "Mondeo"
        assert vc.year is None

    def test_full(self):
        vc = VehicleCreate(make="Ford", model="Mondeo", year=2020, registration="1234ABC",
                           nickname="el coche", vin="WF0XXX")
        assert vc.nickname == "el coche"
        assert vc.vin == "WF0XXX"


class TestVehicle:
    def test_display_name_with_nickname(self):
        v = Vehicle(id=uuid4(), user_id="u1", make="Ford", model="Mondeo",
                    year=2020, registration="1234ABC", nickname="el coche",
                    vin=None, created_at=datetime.now(tz=timezone.utc))
        assert v.display_name == "el coche Ford Mondeo"

    def test_display_name_without_nickname(self):
        v = Vehicle(id=uuid4(), user_id="u1", make="Ford", model="Mondeo",
                    year=None, registration=None, nickname=None,
                    vin=None, created_at=datetime.now(tz=timezone.utc))
        assert v.display_name == "Ford Mondeo"


class TestVehicleMaintenanceCreate:
    def test_valid(self):
        mc = VehicleMaintenanceCreate(
            vehicle_id=uuid4(), date=date(2026, 8, 12),
            description="Cambio de aceite", mileage_km=124350,
        )
        assert mc.mileage_km == 124350
        assert mc.work_performed == []


class TestVehicleResolution:
    def test_found(self):
        v = Vehicle(id=uuid4(), user_id="u1", make="Ford", model="Mondeo",
                    year=None, registration=None, nickname=None,
                    vin=None, created_at=datetime.now(tz=timezone.utc))
        r = VehicleResolution(status="found", vehicle=v)
        assert r.status == "found"
        assert r.vehicle is not None

    def test_not_found(self):
        r = VehicleResolution(status="not_found", message="No encontrado")
        assert r.status == "not_found"
        assert r.vehicle is None

    def test_ambiguous(self):
        v1 = Vehicle(id=uuid4(), user_id="u1", make="Ford", model="Mondeo",
                     year=None, registration=None, nickname=None,
                     vin=None, created_at=datetime.now(tz=timezone.utc))
        v2 = Vehicle(id=uuid4(), user_id="u1", make="Ford", model="Focus",
                     year=None, registration=None, nickname=None,
                     vin=None, created_at=datetime.now(tz=timezone.utc))
        r = VehicleResolution(status="ambiguous", candidates=[v1, v2])
        assert len(r.candidates) == 2