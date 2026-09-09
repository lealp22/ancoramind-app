"""Integration tests for VehiclesRepository against real PostgreSQL (specs/009)."""

import pytest

from src.domain.vehicles.models import VehicleCreate
from src.repositories.vehicles import VehiclesRepository

pytestmark = pytest.mark.integration


async def test_create_get_list_find(session, user_a, user_b):
    repo = VehiclesRepository(session)

    v = await repo.create(
        user_a,
        VehicleCreate(
            make="Ford",
            model="Mondeo",
            year=2019,
            registration="1234ABC",
            nickname="mi coche",
        ),
    )
    assert v.id is not None
    assert v.created_at.tzinfo is not None

    fetched = await repo.get_by_id(user_a, v.id)
    assert fetched is not None
    assert fetched.registration == "1234ABC"

    # Other users cannot see it
    assert await repo.get_by_id(user_b, v.id) is None

    await repo.create(user_a, VehicleCreate(make="Renault", model="Kangoo"))

    assert len(await repo.list_by_user(user_a)) == 2
    assert await repo.list_by_user(user_b) == []

    # find_by_reference matches make/model/nickname/registration (ILIKE)
    assert len(await repo.find_by_reference(user_a, "mondeo")) == 1
    assert len(await repo.find_by_reference(user_a, "KANGOO")) == 1
    assert len(await repo.find_by_reference(user_a, "1234abc")) == 1
    assert await repo.find_by_reference(user_b, "ford") == []
    assert await repo.find_by_reference(user_a, "no-existe") == []
