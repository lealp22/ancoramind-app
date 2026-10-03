"""Reminder domain models."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class ReminderCreate(BaseModel):
    """Input for creating a reminder."""

    title: str = Field(..., min_length=1, max_length=500)
    description: str | None = Field(default=None)
    trigger_at: datetime
    source_document_id: UUID | None = None
    source_action_id: UUID | None = None

    @field_validator("trigger_at")
    @classmethod
    def _trigger_at_must_be_aware(cls, value: datetime) -> datetime:
        """Defense-in-depth: callers must normalize to UTC before this point.

        The service layer resolves the user's timezone and converts naive
        input via ``domain.preferences.timezone.to_utc`` (specs/023 T5.2) —
        this model never resolves a timezone itself, it just refuses to
        persist an ambiguous naive value that slipped through.
        """
        if value.tzinfo is None:
            raise ValueError(
                "trigger_at debe ser timezone-aware (normalizar con "
                "domain.preferences.timezone.to_utc antes de crear el modelo)"
            )
        return value


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
