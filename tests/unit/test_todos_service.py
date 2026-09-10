"""Unit tests for Todos domain service (with mocked repository)."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.domain.todos.models import TodoItem, TodoList
from src.domain.todos.service import TodosService
from src.repositories.todos import TodosRepository
from src.security.user_context import UserContext


@pytest.fixture
def user_ctx():
    return UserContext(user_id="test-user-1")


@pytest.fixture
def mock_repo():
    return AsyncMock(spec=TodosRepository)


@pytest.fixture
def service(mock_repo):
    return TodosService(mock_repo)


def _make_list(user_id="test-user-1", name="Trabajo"):
    now = datetime.now(tz=UTC)
    return TodoList(
        id=uuid4(), user_id=user_id, name=name,
        created_at=now, updated_at=now,
    )


def _make_item(list_id, user_id="test-user-1", title="Tarea 1"):
    now = datetime.now(tz=UTC)
    return TodoItem(
        id=uuid4(), list_id=list_id, user_id=user_id, title=title,
        description=None, status="pending", priority=None,
        due_date=None, position=0, created_at=now, updated_at=now,
    )


class TestTodoLists:
    async def test_create_list(self, service, mock_repo, user_ctx):
        expected = _make_list(name="Trabajo")
        mock_repo.create_list.return_value = expected

        result = await service.create_list(user_ctx, "Trabajo")

        assert result == expected
        mock_repo.create_list.assert_awaited_once()
        call = mock_repo.create_list.call_args
        assert call.args[0] == "test-user-1"
        assert call.args[1].name == "Trabajo"

    async def test_create_list_strips_name(self, service, mock_repo, user_ctx):
        mock_repo.create_list.return_value = _make_list(name="Trabajo")

        await service.create_list(user_ctx, "  Trabajo  ")

        call = mock_repo.create_list.call_args
        assert call.args[1].name == "Trabajo"

    async def test_list_lists(self, service, mock_repo, user_ctx):
        expected = [_make_list(name="Trabajo"), _make_list(name="Personal")]
        mock_repo.list_lists.return_value = expected

        result = await service.list_lists(user_ctx)

        assert result == expected
        mock_repo.list_lists.assert_awaited_once_with("test-user-1")

    async def test_rename_list(self, service, mock_repo, user_ctx):
        list_id = uuid4()
        expected = _make_list(name="Nuevo")
        mock_repo.rename_list.return_value = expected

        result = await service.rename_list(user_ctx, list_id, "Nuevo")

        assert result == expected
        call = mock_repo.rename_list.call_args
        assert call.args[0] == "test-user-1"
        assert call.args[1] == list_id
        assert call.args[2].name == "Nuevo"

    async def test_delete_list(self, service, mock_repo, user_ctx):
        list_id = uuid4()
        mock_repo.delete_list.return_value = True

        result = await service.delete_list(user_ctx, list_id)

        assert result is True
        mock_repo.delete_list.assert_awaited_once_with("test-user-1", list_id)

    async def test_uses_trusted_user_context(self, service, mock_repo):
        ctx = UserContext(user_id="trusted-user-from-channel")
        mock_repo.create_list.return_value = _make_list(
            user_id="trusted-user-from-channel"
        )

        await service.create_list(ctx, "Trabajo")

        call = mock_repo.create_list.call_args
        assert call.args[0] == "trusted-user-from-channel"


class TestTodoItems:
    async def test_add_item(self, service, mock_repo, user_ctx):
        list_id = uuid4()
        expected = _make_item(list_id, title="Preparar presentación")
        mock_repo.create_item.return_value = expected

        result = await service.add_item(
            user_ctx, list_id, "Preparar presentación", priority="high"
        )

        assert result == expected
        call = mock_repo.create_item.call_args
        assert call.args[0] == "test-user-1"
        assert call.args[1] == list_id
        assert call.args[2].title == "Preparar presentación"
        assert call.args[2].priority == "high"

    async def test_add_item_returns_none_for_foreign_list(
        self, service, mock_repo, user_ctx
    ):
        mock_repo.create_item.return_value = None

        result = await service.add_item(user_ctx, uuid4(), "Tarea")

        assert result is None

    async def test_list_items_with_filters(self, service, mock_repo, user_ctx):
        list_id = uuid4()
        expected = [_make_item(list_id)]
        mock_repo.list_items.return_value = expected

        result = await service.list_items(
            user_ctx, list_id, status="pending", priority="high"
        )

        assert result == expected
        mock_repo.list_items.assert_awaited_once_with(
            "test-user-1", list_id, status="pending", priority="high"
        )

    async def test_list_items_rejects_bad_status(self, service, user_ctx):
        with pytest.raises(ValueError, match="status"):
            await service.list_items(user_ctx, uuid4(), status="urgent")

    async def test_list_items_rejects_bad_priority(self, service, user_ctx):
        with pytest.raises(ValueError, match="priority"):
            await service.list_items(user_ctx, uuid4(), priority="urgent")

    async def test_update_item(self, service, mock_repo, user_ctx):
        item_id = uuid4()
        expected = _make_item(uuid4(), title="Nuevo título")
        mock_repo.update_item.return_value = expected

        result = await service.update_item(user_ctx, item_id, title="Nuevo título")

        assert result == expected
        call = mock_repo.update_item.call_args
        assert call.args[0] == "test-user-1"
        assert call.args[1] == item_id
        assert call.args[2].title == "Nuevo título"

    async def test_set_item_status_done(self, service, mock_repo, user_ctx):
        item_id = uuid4()
        expected = _make_item(uuid4(), title="Hecha")
        expected.status = "done"
        mock_repo.set_item_status.return_value = expected

        result = await service.set_item_status(user_ctx, item_id, "done")

        assert result.status == "done"
        mock_repo.set_item_status.assert_awaited_once_with(
            "test-user-1", item_id, "done"
        )

    async def test_set_item_status_rejects_bad_status(self, service, user_ctx):
        with pytest.raises(ValueError, match="status"):
            await service.set_item_status(user_ctx, uuid4(), "archived")

    async def test_move_item(self, service, mock_repo, user_ctx):
        item_id, target = uuid4(), uuid4()
        expected = _make_item(target, title="Movida")
        mock_repo.move_item.return_value = expected

        result = await service.move_item(user_ctx, item_id, target)

        assert result.list_id == target
        mock_repo.move_item.assert_awaited_once_with("test-user-1", item_id, target)

    async def test_delete_item(self, service, mock_repo, user_ctx):
        item_id = uuid4()
        mock_repo.delete_item.return_value = True

        result = await service.delete_item(user_ctx, item_id)

        assert result is True
        mock_repo.delete_item.assert_awaited_once_with("test-user-1", item_id)
