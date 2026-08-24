"""Domain models for personal notes.

Pydantic models — validated, serializable, framework-independent.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class NoteCreate(BaseModel):
    """Input model for creating a new note."""

    content: str = Field(..., min_length=1, max_length=5000)


class Note(BaseModel):
    """A personal note stored in canonical memory."""

    id: UUID
    user_id: str
    content: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}