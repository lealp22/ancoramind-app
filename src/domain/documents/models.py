"""Document domain models — Pydantic schemas for documents and AI extractions."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel


class DocumentCreate(BaseModel):
    """Input for registering a stored document."""

    storage_key: str
    original_filename: str
    mime_type: str
    size_bytes: int
    content_hash: str
    """SHA-256 hex digest of the raw content, used for per-user deduplication."""


class Document(BaseModel):
    """A document stored in AncoraMind's document memory."""

    id: UUID
    user_id: str
    storage_key: str
    original_filename: str
    mime_type: str
    size_bytes: int
    content_hash: str | None = None
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


class DocumentSearchChunkUpsert(BaseModel):
    """One bounded semantic-retrieval representation for a document."""

    document_id: UUID
    user_id: str
    extraction_id: UUID | None = None
    chunk_index: int = 0
    content_hash: str
    index_text: str
    embedding: tuple[float, ...] | None = None
    embedding_provider: str | None = None
    embedding_model: str
    embedding_dimensions: int
    status: str
    error_class: str | None = None


class SemanticDocumentMatch(BaseModel):
    """A user-scoped document selected by vector similarity."""

    document: Document
    distance: float
