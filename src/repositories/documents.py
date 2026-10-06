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
    DocumentSearchChunkUpsert,
    DocumentWithExtraction,
    SemanticDocumentMatch,
)


class DocumentsRepository:
    """Repository for documents and AI extractions in ancora schema."""

    def __init__(self, session: AsyncSession, *, auto_commit: bool = True):
        self._session = session
        self._auto_commit = auto_commit

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
        result = await self._session.execute(
            stmt,
            {
                "user_id": user_id,
                "storage_key": data.storage_key,
                "filename": data.original_filename,
                "mime": data.mime_type,
                "size": data.size_bytes,
                "now": now,
            },
        )
        row = result.fetchone()
        if row is None:
            raise RuntimeError("Document insert did not return a row")
        if self._auto_commit:
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
            id=row.id,
            user_id=row.user_id,
            storage_key=row.storage_key,
            original_filename=row.original_filename,
            mime_type=row.mime_type,
            size_bytes=row.size_bytes,
            created_at=row.created_at,
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
                id=row.id,
                user_id=row.user_id,
                storage_key=row.storage_key,
                original_filename=row.original_filename,
                mime_type=row.mime_type,
                size_bytes=row.size_bytes,
                created_at=row.created_at,
            )
            for row in result.fetchall()
        ]

    async def delete(self, user_id: str, document_id: UUID) -> bool:
        """Delete a document record (user-scoped). Returns True if deleted."""
        stmt = text("DELETE FROM ancora.documents WHERE id=:id AND user_id=:user_id RETURNING id")
        result = await self._session.execute(stmt, {"id": document_id, "user_id": user_id})
        if self._auto_commit:
            await self._session.commit()
        return result.fetchone() is not None

    # ── Semantic retrieval ──────────────────────────────

    async def upsert_search_chunk(self, data: DocumentSearchChunkUpsert) -> None:
        """Persist an idempotent vector index row without exposing its text in logs."""
        await self._session.execute(
            text("""
                INSERT INTO ancora.document_search_chunks (
                    document_id, user_id, extraction_id, chunk_index, content_hash,
                    index_text, embedding, embedding_provider, embedding_model,
                    embedding_dimensions, status, error_class, updated_at
                ) VALUES (
                    :document_id, :user_id, :extraction_id, :chunk_index, :content_hash,
                    :index_text, CAST(:embedding AS vector), :embedding_provider, :embedding_model,
                    :embedding_dimensions, :status, :error_class, :now
                )
                ON CONFLICT (document_id, chunk_index, embedding_model, embedding_dimensions)
                DO UPDATE SET
                    extraction_id = EXCLUDED.extraction_id,
                    content_hash = EXCLUDED.content_hash,
                    index_text = EXCLUDED.index_text,
                    embedding = EXCLUDED.embedding,
                    embedding_provider = EXCLUDED.embedding_provider,
                    status = EXCLUDED.status,
                    error_class = EXCLUDED.error_class,
                    updated_at = EXCLUDED.updated_at
            """),
            {
                "document_id": data.document_id,
                "user_id": data.user_id,
                "extraction_id": data.extraction_id,
                "chunk_index": data.chunk_index,
                "content_hash": data.content_hash,
                "index_text": data.index_text,
                "embedding": _vector_literal(data.embedding),
                "embedding_provider": data.embedding_provider,
                "embedding_model": data.embedding_model,
                "embedding_dimensions": data.embedding_dimensions,
                "status": data.status,
                "error_class": data.error_class,
                "now": datetime.now(tz=UTC),
            },
        )
        if self._auto_commit:
            await self._session.commit()

    async def search_semantically(
        self,
        *,
        user_id: str,
        embedding: tuple[float, ...],
        embedding_model: str,
        embedding_dimensions: int,
        limit: int = 10,
    ) -> list[SemanticDocumentMatch]:
        """Search completed index rows by cosine distance, strictly user-scoped."""
        result = await self._session.execute(
            text("""
                SELECT * FROM (
                    SELECT DISTINCT ON (d.id)
                    d.id, d.user_id, d.storage_key, d.original_filename,
                    d.mime_type, d.size_bytes, d.created_at,
                    c.embedding <=> CAST(:embedding AS vector) AS distance
                    FROM ancora.document_search_chunks c
                    JOIN ancora.documents d ON d.id = c.document_id
                    WHERE c.user_id = :user_id
                      AND d.user_id = :user_id
                      AND c.status = 'completed'
                      AND c.embedding IS NOT NULL
                      AND c.embedding_model = :embedding_model
                      AND c.embedding_dimensions = :embedding_dimensions
                    ORDER BY d.id, c.embedding <=> CAST(:embedding AS vector), d.created_at DESC
                ) matches
                ORDER BY distance ASC, created_at DESC
                LIMIT :limit
            """),
            {
                "user_id": user_id,
                "embedding": _vector_literal(embedding),
                "embedding_model": embedding_model,
                "embedding_dimensions": embedding_dimensions,
                "limit": max(1, min(limit, 20)),
            },
        )
        rows = result.fetchall()
        matches = [
            SemanticDocumentMatch(
                document=Document(
                    id=row.id,
                    user_id=row.user_id,
                    storage_key=row.storage_key,
                    original_filename=row.original_filename,
                    mime_type=row.mime_type,
                    size_bytes=row.size_bytes,
                    created_at=row.created_at,
                ),
                distance=float(row.distance),
            )
            for row in rows
        ]
        return matches

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
        result = await self._session.execute(
            stmt,
            {
                "doc_id": data.document_id,
                "prov": data.provider,
                "model": data.model,
                "pv": data.prompt_version,
                "sv": data.schema_version,
                "extraction": json.dumps(data.extraction),
                "conf": confidence,
                "now": now,
            },
        )
        row = result.fetchone()
        if row is None:
            raise RuntimeError("AI extraction insert did not return a row")
        if self._auto_commit:
            await self._session.commit()
        return AIExtraction(
            id=row.id,
            document_id=data.document_id,
            provider=row.provider,
            model=row.model,
            prompt_version=row.prompt_version,
            schema_version=row.schema_version,
            extraction=row.extraction,
            confidence=row.confidence,
            created_at=row.created_at,
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
            id=row.id,
            document_id=row.document_id,
            provider=row.provider,
            model=row.model,
            prompt_version=row.prompt_version,
            schema_version=row.schema_version,
            extraction=row.extraction,
            confidence=row.confidence,
            created_at=row.created_at,
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


def _vector_literal(embedding: tuple[float, ...] | None) -> str | None:
    """Return a pgvector input value for a bound SQL parameter, never SQL text."""
    if embedding is None:
        return None
    return "[" + ",".join(format(value, ".9g") for value in embedding) + "]"
