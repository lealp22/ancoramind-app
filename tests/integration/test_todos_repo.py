"""Integration tests for TodosRepository against real PostgreSQL (BL-21)."""

import pytest

from src.domain.todos.models import TodoItemCreate, TodoListCreate
from src.repositories.todos import TodosRepository

pytestmark = pytest.mark.integration


async def _make_list(repo, user, name="Trabajo"):
    return await repo.create_list(user, TodoListCreate(name=name))


async def test_create_and_list_lists(session, user_a):
    repo = TodosRepository(session)

    created = await _make_list(repo, user_a, "Trabajo")
    assert created.id is not None
    assert created.user_id == user_a
    assert created.name == "Trabajo"

    await _make_list(repo, user_a, "Personal")

    lists = await repo.list_lists(user_a)
    assert [lst.name for lst in lists] == ["Personal", "Trabajo"]


async def test_lists_are_user_scoped(session, user_a, user_b):
    repo = TodosRepository(session)

    await _make_list(repo, user_a, "Privada")

    assert await repo.list_lists(user_b) == []


async def test_rename_and_delete_list(session, user_a):
    repo = TodosRepository(session)
    from src.domain.todos.models import TodoListRename

    created = await _make_list(repo, user_a, "Compra")
    renamed = await repo.rename_list(
        user_a, created.id, TodoListRename(name="Supermercado")
    )
    assert renamed is not None
    assert renamed.name == "Supermercado"

    assert await repo.delete_list(user_a, created.id) is True
    assert await repo.get_list(user_a, created.id) is None


async def test_item_lifecycle(session, user_a):
    repo = TodosRepository(session)
    lst = await _make_list(repo, user_a, "Trabajo")

    first = await repo.create_item(
        user_a, lst.id, TodoItemCreate(title="Informe", priority="high")
    )
    assert first is not None
    assert first.position == 0
    assert first.status == "pending"

    second = await repo.create_item(
        user_a, lst.id, TodoItemCreate(title="Llamar al cliente")
    )
    assert second is not None
    assert second.position == 1

    items = await repo.list_items(user_a, lst.id)
    assert items is not None
    assert [i.title for i in items] == ["Informe", "Llamar al cliente"]

    pending = await repo.list_items(user_a, lst.id, status="pending")
    assert pending is not None
    assert len(pending) == 2

    high = await repo.list_items(user_a, lst.id, priority="high")
    assert high is not None
    assert [i.title for i in high] == ["Informe"]

    done = await repo.set_item_status(user_a, first.id, "done")
    assert done is not None
    assert done.status == "done"

    done_only = await repo.list_items(user_a, lst.id, status="done")
    assert done_only is not None
    assert [i.title for i in done_only] == ["Informe"]

    from src.domain.todos.models import TodoItemUpdate

    updated = await repo.update_item(
        user_a, second.id, TodoItemUpdate(title="Llamar al cliente VIP")
    )
    assert updated is not None
    assert updated.title == "Llamar al cliente VIP"

    assert await repo.delete_item(user_a, first.id) is True
    remaining = await repo.list_items(user_a, lst.id)
    assert remaining is not None
    assert [i.title for i in remaining] == ["Llamar al cliente VIP"]


async def test_items_are_user_scoped(session, user_a, user_b):
    repo = TodosRepository(session)
    lst = await _make_list(repo, user_a, "Privada")
    created = await repo.create_item(
        user_a, lst.id, TodoItemCreate(title="Secreto")
    )
    assert created is not None

    assert await repo.create_item(
        user_b, lst.id, TodoItemCreate(title="Intruso")
    ) is None
    assert await repo.list_items(user_b, lst.id) is None
    assert await repo.get_item(user_b, created.id) is None
    assert await repo.delete_list(user_b, lst.id) is False


async def test_move_item_between_lists(session, user_a):
    repo = TodosRepository(session)
    work = await _make_list(repo, user_a, "Trabajo")
    personal = await _make_list(repo, user_a, "Personal")
    item = await repo.create_item(
        user_a, work.id, TodoItemCreate(title="Regalo")
    )
    assert item is not None

    moved = await repo.move_item(user_a, item.id, personal.id)
    assert moved is not None
    assert moved.list_id == personal.id

    assert await repo.list_items(user_a, work.id) == []
    dest = await repo.list_items(user_a, personal.id)
    assert dest is not None
    assert [i.title for i in dest] == ["Regalo"]


async def test_delete_list_cascades_items(session, user_a):
    repo = TodosRepository(session)
    lst = await _make_list(repo, user_a, "Temporal")
    item = await repo.create_item(
        user_a, lst.id, TodoItemCreate(title="Efímera")
    )
    assert item is not None

    assert await repo.delete_list(user_a, lst.id) is True
    assert await repo.get_item(user_a, item.id) is None
