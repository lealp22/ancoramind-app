"""Todo domain service — business logic for todo lists and items.

Framework-independent. Can be invoked from: Agno Tool, REST API, CLI, etc.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from src.domain.todos.models import (
    TodoItem,
    TodoItemCreate,
    TodoItemUpdate,
    TodoList,
    TodoListCreate,
    TodoListRename,
)
from src.repositories.todos import TodosRepository
from src.security.user_context import UserContext

_VALID_ITEM_STATUSES = ("pending", "done")
_VALID_PRIORITIES = ("low", "normal", "high")


class TodosService:
    """Service for managing user todo lists and their items."""

    def __init__(self, repository: TodosRepository):
        self._repo = repository

    # ── Lists ──────────────────────────────────────────────

    async def create_list(
        self,
        user_context: UserContext,
        name: str,
    ) -> TodoList:
        """Create a new todo list for the user."""
        data = TodoListCreate(name=name.strip())
        return await self._repo.create_list(user_context.user_id, data)

    async def list_lists(self, user_context: UserContext) -> list[TodoList]:
        """List all todo lists for the user, newest first."""
        return await self._repo.list_lists(user_context.user_id)

    async def rename_list(
        self,
        user_context: UserContext,
        list_id: UUID,
        name: str,
    ) -> TodoList | None:
        """Rename a todo list owned by the user."""
        data = TodoListRename(name=name.strip())
        return await self._repo.rename_list(user_context.user_id, list_id, data)

    async def delete_list(self, user_context: UserContext, list_id: UUID) -> bool:
        """Delete a todo list (and its items) owned by the user."""
        return await self._repo.delete_list(user_context.user_id, list_id)

    # ── Items ──────────────────────────────────────────────

    async def add_item(
        self,
        user_context: UserContext,
        list_id: UUID,
        title: str,
        description: str | None = None,
        priority: str | None = None,
        due_date: datetime | None = None,
    ) -> TodoItem | None:
        """Add an item to a list owned by the user.

        Returns None when the list does not exist (or belongs to another user).
        """
        data = TodoItemCreate(
            title=title.strip(),
            description=description.strip() if description else None,
            priority=priority,
            due_date=due_date,
        )
        return await self._repo.create_item(user_context.user_id, list_id, data)

    async def list_items(
        self,
        user_context: UserContext,
        list_id: UUID,
        status: str | None = None,
        priority: str | None = None,
    ) -> list[TodoItem] | None:
        """List items of a user-owned list, with optional filters.

        Returns None when the list does not exist (or belongs to another user).
        """
        if status is not None and status not in _VALID_ITEM_STATUSES:
            raise ValueError(f"status must be one of {_VALID_ITEM_STATUSES}")
        if priority is not None and priority not in _VALID_PRIORITIES:
            raise ValueError(f"priority must be one of {_VALID_PRIORITIES}")
        return await self._repo.list_items(
            user_context.user_id, list_id, status=status, priority=priority
        )

    async def update_item(
        self,
        user_context: UserContext,
        item_id: UUID,
        title: str | None = None,
        description: str | None = None,
        priority: str | None = None,
        due_date: datetime | None = None,
    ) -> TodoItem | None:
        """Edit an item owned by the user (partial update)."""
        data = TodoItemUpdate(
            title=title.strip() if title else None,
            description=description.strip() if description else description,
            priority=priority,
            due_date=due_date,
        )
        return await self._repo.update_item(user_context.user_id, item_id, data)

    async def set_item_status(
        self,
        user_context: UserContext,
        item_id: UUID,
        status: str,
    ) -> TodoItem | None:
        """Mark an item as pending or done."""
        if status not in _VALID_ITEM_STATUSES:
            raise ValueError(f"status must be one of {_VALID_ITEM_STATUSES}")
        return await self._repo.set_item_status(user_context.user_id, item_id, status)

    async def move_item(
        self,
        user_context: UserContext,
        item_id: UUID,
        target_list_id: UUID,
    ) -> TodoItem | None:
        """Move an item to another list owned by the same user."""
        return await self._repo.move_item(user_context.user_id, item_id, target_list_id)

    async def delete_item(self, user_context: UserContext, item_id: UUID) -> bool:
        """Delete an item owned by the user."""
        return await self._repo.delete_item(user_context.user_id, item_id)
