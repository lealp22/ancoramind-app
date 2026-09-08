"""Reminder domain models."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class ReminderCreate(BaseModel):
    """Input for creating a reminder."""

    title: str = Field(..., min_length=1, max_length=500)
    description: str | None = Field(default=None)
    trigger_at: datetime
    source_document_id: UUID | None = None
    source_action_id: UUID | None = None


class Reminder(BaseModel):
    """A reminder stored in canonical memory."""

    id: UUID
    user_id: str
    title: str
    description: str | None
    trigger_at: datetime
    status: str  # pending, fired, dismissed
    source_document_id: UUID | None
    source_action_id: UUID | None
    created_at: datetime

    model_config = {"from_attributes": True}
