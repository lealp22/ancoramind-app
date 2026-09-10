"""Unit tests for Todo domain models."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.domain.todos.models import (
    TodoItem,
    TodoItemCreate,
    TodoItemUpdate,
    TodoList,
    TodoListCreate,
    TodoListRename,
)


class TestTodoListModels:
    def test_create_valid(self):
        data = TodoListCreate(name="Trabajo")
        assert data.name == "Trabajo"

    def test_create_rejects_empty(self):
        with pytest.raises(ValidationError):
            TodoListCreate(name="")

    def test_create_rejects_too_long(self):
        with pytest.raises(ValidationError):
            TodoListCreate(name="x" * 201)

    def test_rename_valid(self):
        data = TodoListRename(name="Personal")
        assert data.name == "Personal"

    def test_list_from_attributes(self):
        now = datetime.now(tz=UTC)
        lst = TodoList(
            id=uuid4(), user_id="u1", name="Trabajo",
            created_at=now, updated_at=now,
        )
        assert lst.name == "Trabajo"


class TestTodoItemModels:
    def test_create_minimal(self):
        data = TodoItemCreate(title="Comprar leche")
        assert data.title == "Comprar leche"
        assert data.priority is None
        assert data.due_date is None

    def test_create_full(self):
        due = datetime.now(tz=UTC)
        data = TodoItemCreate(
            title="Informe", description="Q3",
            priority="high", due_date=due,
        )
        assert data.priority == "high"
        assert data.due_date == due

    def test_create_rejects_bad_priority(self):
        with pytest.raises(ValidationError):
            TodoItemCreate(title="T", priority="urgent")

    def test_create_rejects_empty_title(self):
        with pytest.raises(ValidationError):
            TodoItemCreate(title="")

    def test_update_partial(self):
        data = TodoItemUpdate(title="Nuevo")
        assert data.title == "Nuevo"
        assert data.priority is None

    def test_update_empty_means_all_none(self):
        data = TodoItemUpdate()
        assert data.title is None
        assert data.description is None

    def test_item_from_attributes(self):
        now = datetime.now(tz=UTC)
        item = TodoItem(
            id=uuid4(), list_id=uuid4(), user_id="u1", title="T",
            description=None, status="pending", priority="low",
            due_date=None, position=0, created_at=now, updated_at=now,
        )
        assert item.status == "pending"
        assert item.position == 0
