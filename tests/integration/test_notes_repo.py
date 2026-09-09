"""Integration tests for NotesRepository against real PostgreSQL (specs/009)."""

import pytest

from src.domain.notes.models import NoteCreate
from src.repositories.notes import NotesRepository

pytestmark = pytest.mark.integration


async def test_create_and_search(session, user_a):
    repo = NotesRepository(session)

    created = await repo.create(user_a, NoteCreate(content="Comprar filtro de aire"))
    assert created.id is not None
    assert created.user_id == user_a
    assert created.content == "Comprar filtro de aire"
    assert created.created_at.tzinfo is not None  # TIMESTAMPTZ is timezone-aware
    assert created.created_at == created.updated_at

    await repo.create(user_a, NoteCreate(content="Renovar seguro del coche"))

    hits = await repo.search(user_a, "filtro")
    assert [n.content for n in hits] == ["Comprar filtro de aire"]

    assert len(await repo.search(user_a)) == 2


async def test_search_is_user_scoped(session, user_a, user_b):
    repo = NotesRepository(session)

    await repo.create(user_a, NoteCreate(content="nota privada de A"))

    assert await repo.search(user_b, "nota privada") == []
    assert await repo.search(user_b) == []


async def test_search_orders_by_created_at_desc(session, user_a):
    repo = NotesRepository(session)

    for i in range(3):
        await repo.create(user_a, NoteCreate(content=f"nota-{i}"))

    results = await repo.search(user_a)
    assert [n.content for n in results] == ["nota-2", "nota-1", "nota-0"]
