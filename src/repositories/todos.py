"""Todos repository — parameterized PostgreSQL access for todo lists + items.

All queries are parameterized. No string interpolation. User-scoped data access.
Ownership of an item is enforced by joining against ancora.todo_lists
(the item's list must belong to the requesting user).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.todos.models import (
    TodoItem,
    TodoItemCreate,
    TodoItemUpdate,
    TodoList,
    TodoListCreate,
    TodoListRename,
)


class TodosRepository:
    """Repository for todo lists and items in the ancora schema."""

    def __init__(self, session: AsyncSession):
        self._session = session

    # ── Lists ──────────────────────────────────────────────

    async def create_list(self, user_id: str, data: TodoListCreate) -> TodoList:
        now = datetime.now(tz=UTC)
        stmt = text("""
            INSERT INTO ancora.todo_lists (user_id, name, created_at, updated_at)
            VALUES (:uid, :name, :now, :now)
            RETURNING id, user_id, name, created_at, updated_at
        """)
        result = await self._session.execute(
            stmt, {"uid": user_id, "name": data.name, "now": now}
        )
        row = result.fetchone()
        await self._session.commit()
        return _row_to_list(row)

    async def list_lists(self, user_id: str) -> list[TodoList]:
        stmt = text("""
            SELECT id, user_id, name, created_at, updated_at
            FROM ancora.todo_lists
            WHERE user_id = :uid
            ORDER BY created_at DESC
        """)
        result = await self._session.execute(stmt, {"uid": user_id})
        return [_row_to_list(row) for row in result.fetchall()]

    async def get_list(self, user_id: str, list_id: UUID) -> TodoList | None:
        stmt = text("""
            SELECT id, user_id, name, created_at, updated_at
            FROM ancora.todo_lists
            WHERE id = :id AND user_id = :uid
        """)
        result = await self._session.execute(stmt, {"id": list_id, "uid": user_id})
        row = result.fetchone()
        return _row_to_list(row) if row else None

    async def rename_list(
        self, user_id: str, list_id: UUID, data: TodoListRename
    ) -> TodoList | None:
        now = datetime.now(tz=UTC)
        stmt = text("""
            UPDATE ancora.todo_lists
            SET name = :name, updated_at = :now
            WHERE id = :id AND user_id = :uid
            RETURNING id, user_id, name, created_at, updated_at
        """)
        result = await self._session.execute(
            stmt, {"name": data.name, "now": now, "id": list_id, "uid": user_id}
        )
        row = result.fetchone()
        await self._session.commit()
        return _row_to_list(row) if row else None

    async def delete_list(self, user_id: str, list_id: UUID) -> bool:
        stmt = text("""
            DELETE FROM ancora.todo_lists
            WHERE id = :id AND user_id = :uid
        """)
        result = await self._session.execute(stmt, {"id": list_id, "uid": user_id})
        await self._session.commit()
        count = getattr(result, "rowcount", 0) or 0
        return bool(count > 0)

    # ── Items ──────────────────────────────────────────────

    async def create_item(
        self, user_id: str, list_id: UUID, data: TodoItemCreate
    ) -> TodoItem | None:
        """Append an item at the end of a user-owned list.

        Returns None when the list does not exist or belongs to another user.
        """
        owner = await self.get_list(user_id, list_id)
        if owner is None:
            return None
        now = datetime.now(tz=UTC)
        stmt = text("""
            INSERT INTO ancora.todo_items
                (list_id, user_id, title, description, status, priority,
                 due_date, position, created_at, updated_at)
            SELECT :insert_lid, :insert_uid, :title, :desc, 'pending', :priority,
                   :due, COALESCE(MAX(position), -1) + 1, :now, :now
            FROM ancora.todo_items
            WHERE list_id = :filter_lid AND user_id = :filter_uid
            RETURNING id, list_id, user_id, title, description, status,
                      priority, due_date, position, created_at, updated_at
        """)
        result = await self._session.execute(
            stmt,
            {
                "insert_lid": list_id, "insert_uid": user_id,
                "filter_lid": list_id, "filter_uid": user_id,
                "title": data.title,
                "desc": data.description, "priority": data.priority,
                "due": data.due_date, "now": now,
            },
        )
        row = result.fetchone()
        await self._session.commit()
        return _row_to_item(row) if row else None

    async def list_items(
        self,
        user_id: str,
        list_id: UUID,
        status: str | None = None,
        priority: str | None = None,
    ) -> list[TodoItem] | None:
        """List items of a list; None when the list is not user-owned."""
        owner = await self.get_list(user_id, list_id)
        if owner is None:
            return None
        clauses = ["list_id = :lid", "user_id = :uid"]
        params: dict[str, Any] = {"lid": list_id, "uid": user_id}
        if status is not None:
            clauses.append("status = :status")
            params["status"] = status
        if priority is not None:
            clauses.append("priority = :priority")
            params["priority"] = priority
        stmt = text(
            "SELECT id, list_id, user_id, title, description, status,"
            " priority, due_date, position, created_at, updated_at"
            " FROM ancora.todo_items"
            f" WHERE {' AND '.join(clauses)}"
            " ORDER BY position, created_at"
        )
        result = await self._session.execute(stmt, params)
        return [_row_to_item(row) for row in result.fetchall()]

    async def get_item(self, user_id: str, item_id: UUID) -> TodoItem | None:
        stmt = text("""
            SELECT id, list_id, user_id, title, description, status,
                   priority, due_date, position, created_at, updated_at
            FROM ancora.todo_items
            WHERE id = :id AND user_id = :uid
        """)
        result = await self._session.execute(stmt, {"id": item_id, "uid": user_id})
        row = result.fetchone()
        return _row_to_item(row) if row else None

    async def update_item(
        self, user_id: str, item_id: UUID, data: TodoItemUpdate
    ) -> TodoItem | None:
        fields: list[str] = []
        params: dict[str, Any] = {"id": item_id, "uid": user_id, "now": datetime.now(tz=UTC)}
        if data.title is not None:
            fields.append("title = :title")
            params["title"] = data.title
        if data.description is not None:
            fields.append("description = :desc")
            params["desc"] = data.description
        if data.priority is not None:
            fields.append("priority = :priority")
            params["priority"] = data.priority
        if data.due_date is not None:
            fields.append("due_date = :due")
            params["due"] = data.due_date
        fields.append("updated_at = :now")
        set_clause = ", ".join(fields)
        stmt = text(
            "UPDATE ancora.todo_items SET " + set_clause + " "
            "WHERE id = :id AND user_id = :uid "
            "RETURNING id, list_id, user_id, title, description, status,"
            " priority, due_date, position, created_at, updated_at"
        )
        result = await self._session.execute(stmt, params)
        row = result.fetchone()
        await self._session.commit()
        return _row_to_item(row) if row else None

    async def set_item_status(
        self, user_id: str, item_id: UUID, status: str
    ) -> TodoItem | None:
        stmt = text("""
            UPDATE ancora.todo_items
            SET status = :status, updated_at = :now
            WHERE id = :id AND user_id = :uid
            RETURNING id, list_id, user_id, title, description, status,
                      priority, due_date, position, created_at, updated_at
        """)
        result = await self._session.execute(
            stmt,
            {"status": status, "now": datetime.now(tz=UTC),
             "id": item_id, "uid": user_id},
        )
        row = result.fetchone()
        await self._session.commit()
        return _row_to_item(row) if row else None

    async def move_item(
        self, user_id: str, item_id: UUID, target_list_id: UUID
    ) -> TodoItem | None:
        """Move an item to another list of the same user (appended at the end)."""
        target = await self.get_list(user_id, target_list_id)
        if target is None:
            return None
        item = await self.get_item(user_id, item_id)
        if item is None:
            return None
        now = datetime.now(tz=UTC)
        stmt = text("""
            UPDATE ancora.todo_items
            SET list_id = :lid, position = :pos, updated_at = :now
            WHERE id = :id AND user_id = :uid
            RETURNING id, list_id, user_id, title, description, status,
                      priority, due_date, position, created_at, updated_at
        """)
        pos_stmt = text("""
            SELECT COALESCE(MAX(position), -1) + 1 AS next_pos
            FROM ancora.todo_items
            WHERE list_id = :lid AND user_id = :uid
        """)
        pos_result = await self._session.execute(
            pos_stmt, {"lid": target_list_id, "uid": user_id}
        )
        pos_row = pos_result.fetchone()
        if pos_row is None:
            return None
        next_pos = pos_row.next_pos
        result = await self._session.execute(
            stmt,
            {"lid": target_list_id, "pos": next_pos, "now": now,
             "id": item_id, "uid": user_id},
        )
        row = result.fetchone()
        await self._session.commit()
        return _row_to_item(row) if row else None

    async def delete_item(self, user_id: str, item_id: UUID) -> bool:
        stmt = text("""
            DELETE FROM ancora.todo_items
            WHERE id = :id AND user_id = :uid
        """)
        result = await self._session.execute(stmt, {"id": item_id, "uid": user_id})
        await self._session.commit()
        count = getattr(result, "rowcount", 0) or 0
        return bool(count > 0)


def _row_to_list(row: Any) -> TodoList:
    return TodoList(
        id=row.id, user_id=row.user_id, name=row.name,
        created_at=row.created_at, updated_at=row.updated_at,
    )


def _row_to_item(row: Any) -> TodoItem:
    return TodoItem(
        id=row.id, list_id=row.list_id, user_id=row.user_id,
        title=row.title, description=row.description, status=row.status,
        priority=row.priority, due_date=row.due_date, position=row.position,
        created_at=row.created_at, updated_at=row.updated_at,
    )

