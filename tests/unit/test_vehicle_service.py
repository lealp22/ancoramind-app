"""Unit tests for Vehicle service (with mocked repositories)."""

from datetime import UTC, date, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.domain.vehicles.models import Vehicle, VehicleCreate
from src.domain.vehicles.service import VehicleService, normalize_registration
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
                   vin=None, created_at=datetime.now(tz=UTC))


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
        mock_vehicles_repo.find_by_reference.return_value = [
            make_vehicle(), make_vehicle(model="Focus")
        ]
        result = await service.find_vehicle(user_ctx, "Ford")
        assert result.status == "ambiguous"
        assert len(result.candidates) == 2

    async def test_no_reference_lists_all(self, service, mock_vehicles_repo, user_ctx):
        v = make_vehicle()
        mock_vehicles_repo.list_by_user.return_value = [v]
        result = await service.find_vehicle(user_ctx, None)
        assert result.status == "found"
        assert result.vehicle == v

    async def test_registration_reference_retries_normalized(
        self, service, mock_vehicles_repo, user_ctx
    ):
        vehicle = make_vehicle()
        vehicle.registration = "6789XYZ"
        mock_vehicles_repo.find_by_reference.side_effect = [[], [vehicle]]

        result = await service.find_vehicle(user_ctx, "6789-xyz")

        assert result.status == "found"
        assert result.vehicle == vehicle
        assert mock_vehicles_repo.find_by_reference.await_args_list == [
            (("test-user", "6789-xyz"),),
            (("test-user", "6789XYZ"),),
        ]

    async def test_regular_reference_does_not_retry_when_already_canonical(
        self, service, mock_vehicles_repo, user_ctx
    ):
        mock_vehicles_repo.find_by_reference.return_value = []

        await service.find_vehicle(user_ctx, "Toyota")

        mock_vehicles_repo.find_by_reference.assert_awaited_once_with(
            "test-user", "Toyota"
        )


class TestRegisterVehicle:
    async def test_happy_path_normalizes(self, service, mock_vehicles_repo, user_ctx):
        v = make_vehicle()
        mock_vehicles_repo.find_by_reference.return_value = []
        mock_vehicles_repo.create.return_value = v

        result = await service.register_vehicle(
            user_ctx,
            VehicleCreate(make="Ford", model="Focus",
                          registration=" 9988-xyz ", nickname="  el focus "),
        )

        assert result == v
        args = mock_vehicles_repo.create.call_args[0]
        # user_id from UserContext, never from caller input
        assert args[0] == "test-user"
        assert args[1].registration == "9988XYZ"
        assert args[1].nickname == "el focus"
        mock_vehicles_repo.find_by_reference.assert_awaited_once_with(
            "test-user", "9988XYZ"
        )

    async def test_duplicate_registration_raises_and_does_not_write(
        self, service, mock_vehicles_repo, user_ctx
    ):
        existing = Vehicle(
            id=uuid4(), user_id="test-user", make="Ford", model="Mondeo",
            year=2019, registration="1234-ABC", nickname=None, vin=None,
            created_at=datetime.now(tz=UTC),
        )
        mock_vehicles_repo.find_by_reference.return_value = [existing]
        mock_vehicles_repo.create = AsyncMock()

        with pytest.raises(ValueError, match="1234-ABC"):
            await service.register_vehicle(
                user_ctx,
                VehicleCreate(make="Ford", model="Focus",
                              registration="1234 abc"),
            )

        mock_vehicles_repo.create.assert_not_awaited()

    async def test_duplicate_comparison_is_normalized(
        self, service, mock_vehicles_repo, user_ctx
    ):
        # stored "AB-123CD" matches incoming "ab123cd" after normalization
        existing = make_vehicle()
        existing.registration = "AB-123CD"
        mock_vehicles_repo.find_by_reference.return_value = [existing]

        with pytest.raises(ValueError):
            await service.register_vehicle(
                user_ctx,
                VehicleCreate(make="Seat", model="Ibiza",
                              registration="ab 123 cd"),
            )

    async def test_no_registration_skips_duplicate_check(
        self, service, mock_vehicles_repo, user_ctx
    ):
        mock_vehicles_repo.create.return_value = make_vehicle()
        await service.register_vehicle(
            user_ctx, VehicleCreate(make="Toyota", model="Corolla")
        )
        mock_vehicles_repo.find_by_reference.assert_not_awaited()
        mock_vehicles_repo.create.assert_awaited_once()


class TestNormalizeRegistration:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("1234ABC", "1234ABC"),
            (" 12-34 abc ", "1234ABC"),
            ("ab-cd/ef", "ABCDEF"),
            ("ab 123 cd", "AB123CD"),
            ("  ---  ", None),
            ("", None),
            (None, None),
        ],
    )
    def test_normalization(self, raw, expected):
        assert normalize_registration(raw) == expected


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
