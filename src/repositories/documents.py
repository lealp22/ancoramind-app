"""Documents repository — parameterized PostgreSQL access for documents."""

import json
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.documents.models import (
    AIExtraction,
    AIExtractionCreate,
    Document,
    DocumentCreate,
    DocumentWithExtraction,
)


class DocumentsRepository:
    """Repository for documents and AI extractions in ancora schema."""

    def __init__(self, session: AsyncSession):
        self._session = session

    # ── Documents ─────────────────────────────────────────

    async def create(self, user_id: str, data: DocumentCreate) -> Document:
        """Create a document record."""
        now = datetime.now(tz=UTC)
        stmt = text("""
            INSERT INTO ancora.documents
                (user_id, storage_key, original_filename, mime_type, size_bytes, created_at)
            VALUES (:user_id, :storage_key, :filename, :mime, :size, :now)
            RETURNING id, user_id, storage_key, original_filename, mime_type, size_bytes, created_at
        """)
        result = await self._session.execute(stmt, {
            "user_id": user_id,
            "storage_key": data.storage_key,
            "filename": data.original_filename,
            "mime": data.mime_type,
            "size": data.size_bytes,
            "now": now,
        })
        row = result.fetchone()
        if row is None:
            raise RuntimeError("Document insert did not return a row")
        await self._session.commit()
        return Document(
            id=row.id,
            user_id=row.user_id,
            storage_key=row.storage_key,
            original_filename=row.original_filename,
            mime_type=row.mime_type,
            size_bytes=row.size_bytes,
            created_at=row.created_at,
        )

    async def get_by_id(self, user_id: str, document_id: UUID) -> Document | None:
        """Get a document by ID (user-scoped)."""
        stmt = text("""
            SELECT id, user_id, storage_key, original_filename,
                   mime_type, size_bytes, created_at
            FROM ancora.documents
            WHERE id = :id AND user_id = :user_id
        """)
        result = await self._session.execute(stmt, {"id": document_id, "user_id": user_id})
        row = result.fetchone()
        if not row:
            return None
        return Document(
            id=row.id, user_id=row.user_id, storage_key=row.storage_key,
            original_filename=row.original_filename, mime_type=row.mime_type,
            size_bytes=row.size_bytes, created_at=row.created_at,
        )

    async def search(
        self, user_id: str, query: str | None = None, limit: int = 20
    ) -> list[Document]:
        """Search documents by filename (ILIKE) or list recent."""
        if query:
            stmt = text("""
                SELECT id, user_id, storage_key, original_filename,
                       mime_type, size_bytes, created_at
                FROM ancora.documents
                WHERE user_id = :user_id AND original_filename ILIKE :pattern
                ORDER BY created_at DESC LIMIT :limit
            """)
            params = {"user_id": user_id, "pattern": f"%{query}%", "limit": limit}
        else:
            stmt = text("""
                SELECT id, user_id, storage_key, original_filename,
                       mime_type, size_bytes, created_at
                FROM ancora.documents
                WHERE user_id = :user_id
                ORDER BY created_at DESC LIMIT :limit
            """)
            params = {"user_id": user_id, "limit": limit}

        result = await self._session.execute(stmt, params)
        return [
            Document(
                id=row.id, user_id=row.user_id, storage_key=row.storage_key,
                original_filename=row.original_filename, mime_type=row.mime_type,
                size_bytes=row.size_bytes, created_at=row.created_at,
            )
            for row in result.fetchall()
        ]

    async def delete(self, user_id: str, document_id: UUID) -> bool:
        """Delete a document record (user-scoped). Returns True if deleted."""
        stmt = text("DELETE FROM ancora.documents WHERE id=:id AND user_id=:user_id RETURNING id")
        result = await self._session.execute(stmt, {"id": document_id, "user_id": user_id})
        await self._session.commit()
        return result.fetchone() is not None
# ── AI Extractions ────────────────────────────────────

    async def create_extraction(self, data: AIExtractionCreate) -> AIExtraction:
        """Store an AI extraction result."""
        now = datetime.now(tz=UTC)
        confidence = data.extraction.get("confidence")
        stmt = text("""
            INSERT INTO ancora.ai_extractions
                (document_id, provider, model, prompt_version,
                 schema_version, extraction, confidence, created_at)
            VALUES (:doc_id,:prov,:model,:pv,:sv,CAST(:extraction AS jsonb),:conf,:now)
            RETURNING id, document_id, provider, model, prompt_version,
                      schema_version, extraction, confidence, created_at
        """)
        result = await self._session.execute(stmt, {
            "doc_id": data.document_id, "prov": data.provider,
            "model": data.model, "pv": data.prompt_version,
            "sv": data.schema_version, "extraction": json.dumps(data.extraction),
            "conf": confidence, "now": now,
        })
        row = result.fetchone()
        if row is None:
            raise RuntimeError("AI extraction insert did not return a row")
        await self._session.commit()
        return AIExtraction(
            id=row.id, document_id=data.document_id, provider=row.provider,
            model=row.model, prompt_version=row.prompt_version,
            schema_version=row.schema_version, extraction=row.extraction,
            confidence=row.confidence, created_at=row.created_at,
        )

    async def get_latest_extraction(self, document_id: UUID) -> AIExtraction | None:
        """Get the latest extraction for a document."""
        stmt = text("""
            SELECT id, document_id, provider, model, prompt_version,
                   schema_version, extraction, confidence, created_at
            FROM ancora.ai_extractions
            WHERE document_id = :doc_id ORDER BY created_at DESC LIMIT 1
        """)
        result = await self._session.execute(stmt, {"doc_id": document_id})
        row = result.fetchone()
        if not row:
            return None
        return AIExtraction(
            id=row.id, document_id=row.document_id, provider=row.provider,
            model=row.model, prompt_version=row.prompt_version,
            schema_version=row.schema_version, extraction=row.extraction,
            confidence=row.confidence, created_at=row.created_at,
        )

    async def get_document_with_extraction(
        self, user_id: str, document_id: UUID
    ) -> DocumentWithExtraction | None:
        """Get a document with its latest extraction."""
        doc = await self.get_by_id(user_id, document_id)
        if not doc:
            return None
        extraction = await self.get_latest_extraction(document_id)
        return DocumentWithExtraction(document=doc, extraction=extraction)
