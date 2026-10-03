"""Calendar domain models."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from src.domain.shared.recurrence import RecurrenceRule


class CalendarEventCreate(BaseModel):
    """Input for creating a calendar event."""

    title: str = Field(..., min_length=1, max_length=500)
    start_at: datetime
    end_at: datetime | None = None
    description: str | None = None
    location: str | None = None
    source_document_id: UUID | None = None
    recurrence_rule: RecurrenceRule | None = None

    @field_validator("start_at", "end_at")
    @classmethod
    def _must_be_aware(cls, value: datetime | None) -> datetime | None:
        """Defense-in-depth: callers must normalize to UTC before this point.

        The service layer resolves the user's timezone and converts naive
        input via ``domain.preferences.timezone.to_utc`` (specs/023 T5.2) —
        this model never resolves a timezone itself, it just refuses to
        persist an ambiguous naive value that slipped through.
        """
        if value is not None and value.tzinfo is None:
            raise ValueError(
                "las fechas deben ser timezone-aware (normalizar con "
                "domain.preferences.timezone.to_utc antes de crear el modelo)"
            )
        return value


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
    recurrence_rule: RecurrenceRule | None = None

    model_config = {"from_attributes": True}
