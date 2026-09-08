"""Calendar domain models."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class CalendarEventCreate(BaseModel):
    """Input for creating a calendar event."""

    title: str = Field(..., min_length=1, max_length=500)
    start_at: datetime
    end_at: datetime | None = None
    description: str | None = None
    location: str | None = None
    source_document_id: UUID | None = None


class CalendarEvent(BaseModel):
    """A calendar event stored canonically."""

    id: UUID
    user_id: str
    title: str
    description: str | None
    location: str | None
    start_at: datetime
    end_at: datetime | None
    provider_event_id: str | None
    source_document_id: UUID | None
    created_at: datetime

    model_config = {"from_attributes": True}
