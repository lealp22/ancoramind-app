"""Todo domain models.

Pydantic models — validated, serializable, framework-independent.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class TodoListCreate(BaseModel):
    """Input for creating a todo list."""

    name: str = Field(..., min_length=1, max_length=200)


class TodoListRename(BaseModel):
    """Input for renaming a todo list."""

    name: str = Field(..., min_length=1, max_length=200)


class TodoList(BaseModel):
    """A named todo list owned by a user."""

    id: UUID
    user_id: str
    name: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class TodoItemCreate(BaseModel):
    """Input for creating a todo item inside a list."""

    title: str = Field(..., min_length=1, max_length=500)
    description: str | None = None
    priority: str | None = Field(default=None, pattern="^(low|normal|high)$")
    due_date: datetime | None = None


class TodoItemUpdate(BaseModel):
    """Input for editing a todo item (partial update)."""

    title: str | None = Field(default=None, min_length=1, max_length=500)
    description: str | None = None
    priority: str | None = Field(default=None, pattern="^(low|normal|high)$")
    due_date: datetime | None = None


class TodoItem(BaseModel):
    """A single task inside a todo list."""

    id: UUID
    list_id: UUID
    user_id: str
    title: str
    description: str | None
    status: str  # pending, done
    priority: str | None  # low, normal, high
    due_date: datetime | None
    position: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
