"""Unit tests for Vehicle service (with mocked repositories)."""

from datetime import date, datetime, timezone
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.domain.vehicles.models import Vehicle
from src.domain.vehicles.service import VehicleService
from src.security.user_context import UserContext


@pytest.fixture
def user_ctx():
    return UserContext(user_id="test-user")


@pytest.fixture
def mock_vehicles_repo():
    return AsyncMock()


@pytest.fixture
def mock_maintenance_repo():
    return AsyncMock()


@pytest.fixture
def service(mock_vehicles_repo, mock_maintenance_repo):
    return VehicleService(mock_vehicles_repo, mock_maintenance_repo)


def make_vehicle(make="Ford", model="Mondeo", nickname=None):
    return Vehicle(id=uuid4(), user_id="test-user", make=make, model=model,
                   year=None, registration=None, nickname=nickname,
                   vin=None, created_at=datetime.now(tz=timezone.utc))


class TestFindVehicle:
    async def test_not_found(self, service, mock_vehicles_repo, user_ctx):
        mock_vehicles_repo.find_by_reference.return_value = []
        result = await service.find_vehicle(user_ctx, "Toyota")
        assert result.status == "not_found"

    async def test_found_single(self, service, mock_vehicles_repo, user_ctx):
        v = make_vehicle()
        mock_vehicles_repo.find_by_reference.return_value = [v]
        result = await service.find_vehicle(user_ctx, "Ford")
        assert result.status == "found"
        assert result.vehicle == v

    async def test_ambiguous(self, service, mock_vehicles_repo, user_ctx):
        mock_vehicles_repo.find_by_reference.return_value = [make_vehicle(), make_vehicle(model="Focus")]
        result = await service.find_vehicle(user_ctx, "Ford")
        assert result.status == "ambiguous"
        assert len(result.candidates) == 2

    async def test_no_reference_lists_all(self, service, mock_vehicles_repo, user_ctx):
        v = make_vehicle()
        mock_vehicles_repo.list_by_user.return_value = [v]
        result = await service.find_vehicle(user_ctx, None)
        assert result.status == "found"
        assert result.vehicle == v


class TestRegisterMaintenance:
    async def test_calls_repo(self, service, mock_maintenance_repo, user_ctx):
        vid = uuid4()
        await service.register_maintenance(
            user_ctx, vid, date(2026, 8, 12), "Cambio de aceite",
            mileage_km=124350, workshop="Taller Martinez",
        )
        mock_maintenance_repo.create.assert_awaited_once()
        # First positional arg is user_id, second is data
        args = mock_maintenance_repo.create.call_args[0]
        assert args[0] == "test-user"
        assert args[1].vehicle_id == vid