"""Document domain models — Pydantic schemas for documents and AI extractions."""

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class DocumentCreate(BaseModel):
    """Input for registering a stored document."""

    storage_key: str
    original_filename: str
    mime_type: str
    size_bytes: int


class Document(BaseModel):
    """A document stored in AncoraMind's document memory."""

    id: UUID
    user_id: str
    storage_key: str
    original_filename: str
    mime_type: str
    size_bytes: int
    created_at: datetime

    model_config = {"from_attributes": True}


class AIExtractionCreate(BaseModel):
    """Input for storing an AI extraction result."""

    document_id: UUID
    provider: str
    model: str
    prompt_version: str
    schema_version: str
    extraction: dict[str, Any]
    """The full extraction JSON (type, summary, fields, confidence, suggested_actions)."""


class AIExtraction(BaseModel):
    """An AI extraction result linked to a document."""

    id: UUID
    document_id: UUID
    provider: str
    model: str
    prompt_version: str
    schema_version: str
    extraction: dict[str, Any]
    confidence: float | None
    created_at: datetime

    model_config = {"from_attributes": True}


class DocumentWithExtraction(BaseModel):
    """A document with its latest AI extraction."""

    document: Document
    extraction: AIExtraction | None