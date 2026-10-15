"""Document domain service — ingestion, storage, extraction, and search.

Framework-independent. Pipeline orchestration for the document lifecycle.
Extraction inference goes through the domain-owned ``DocumentExtractionPort``
(specs/013 T9); no runtime framework is imported here.
"""

import json
import logging
from hashlib import sha256
from uuid import UUID

from sqlalchemy.exc import SQLAlchemyError

from src.domain.documents.embeddings import DocumentEmbeddingPort
from src.domain.documents.extraction import DocumentExtractionPort, DocumentVisualPage
from src.domain.documents.models import (
    AIExtraction,
    AIExtractionCreate,
    Document,
    DocumentCreate,
    DocumentSearchChunkUpsert,
    DocumentWithExtraction,
    SemanticDocumentMatch,
)
from src.domain.documents.schemas import GenericDocumentExtraction
from src.observability.telemetry import get_telemetry
from src.repositories.documents import DocumentsRepository
from src.security.user_context import UserContext
from src.storage.base import DocumentStorage

logger = logging.getLogger(__name__)


class DocumentService:
    """Service for managing the document lifecycle."""

    EXTRACTION_PROMPT_VERSION = "1.2"
    EXTRACTION_SCHEMA_VERSION = "1.1"
    MAX_TEXT_PREVIEW_BYTES = 5000
    MAX_INDEX_TEXT_CHARS = 6000
    INDEX_TEXT_VERSION = "1"

    def __init__(
        self,
        repository: DocumentsRepository,
        storage: DocumentStorage,
        extraction_port: DocumentExtractionPort,
        embedding_port: DocumentEmbeddingPort | None = None,
    ) -> None:
        self._repo = repository
        self._storage = storage
        self._extraction_port = extraction_port
        self._embedding_port = embedding_port

    # ── Pipeline ────────────────────────────────────────

    async def ingest(
        self,
        user_context: UserContext,
        content: bytes,
        filename: str,
        mime_type: str,
        visual_pages: tuple[DocumentVisualPage, ...] = (),
        extracted_text: str | None = None,
    ) -> DocumentWithExtraction:
        """Full document pipeline: store → register → extract.

        All steps are automatic per Architecture §17:
        receive, store, register metadata, analyze, save extraction.

        ``extracted_text`` carries Markdown deterministically extracted from a
        PDF's own text layer (specs/021 T2) by the infrastructure layer. It is
        untrusted document content, handled the same way as the ``text/*``
        preview below — bounded and serialized as data, never as instructions.

        Returns:
            Document with its AI extraction. If the same user already uploaded
            this exact content, the existing document and extraction are
            returned without storing or extracting again (BL-31).
        """
        content_hash = sha256(content).hexdigest()
        existing = await self._repo.get_by_content_hash(
            user_id=user_context.user_id, content_hash=content_hash
        )
        if existing is not None:
            reused = await self._repo.get_document_with_extraction(
                user_id=user_context.user_id, document_id=existing.id
            )
            if reused is not None:
                return reused

        # 1. Store original
        stored = await self._storage.store(content, filename, mime_type)

        # 2. Register document record
        doc = await self._repo.create(
            user_id=user_context.user_id,
            data=DocumentCreate(
                storage_key=stored.storage_key,
                original_filename=stored.original_filename,
                mime_type=stored.mime_type,
                size_bytes=stored.size_bytes,
                content_hash=content_hash,
            ),
        )

        # 3. AI extraction (for text-based documents)
        extraction = await self._extract(doc, content, visual_pages, extracted_text)
        await self._index_for_semantic_retrieval(doc, extraction)

        return DocumentWithExtraction(document=doc, extraction=extraction)

    async def _extract(
        self,
        doc: Document,
        content: bytes,
        visual_pages: tuple[DocumentVisualPage, ...],
        extracted_text: str | None = None,
    ) -> AIExtraction | None:
        """Run AI extraction through the governed port.

        Visual pages are transient input from the infrastructure layer. They are
        never persisted in the extraction audit or exported to observability.
        """
        if visual_pages:
            extraction_route = "visual"
        elif extracted_text:
            extraction_route = "deterministic"
        else:
            extraction_route = "none"
        get_telemetry().counter(
            "ancora.document.extraction_route",
            attributes={"ancora.document.extraction_route": extraction_route},
        )
        prompt = self._build_extraction_prompt(
            doc,
            content,
            visual_pages_attached=bool(visual_pages),
            extracted_text=extracted_text,
        )
        if visual_pages:
            outcome = await self._extraction_port.extract(
                prompt=prompt,
                schema=GenericDocumentExtraction,
                visual_pages=visual_pages,
            )
        else:
            outcome = await self._extraction_port.extract(
                prompt=prompt,
                schema=GenericDocumentExtraction,
            )

        if outcome.status != "completed" or outcome.extraction is None:
            # Observable, content-free failure metadata: the document stays
            # archived while the extraction gap remains auditable. T9 removes
            # the previous silent swallowing of inference failures.
            logger.warning(
                "Document extraction did not complete "
                "(document_id=%s, status=%s, error_class=%s, provider=%s, model=%s)",
                doc.id,
                outcome.status,
                outcome.error_class,
                outcome.provider,
                outcome.model,
            )
            return None

        return await self._repo.create_extraction(
            AIExtractionCreate(
                document_id=doc.id,
                provider=outcome.provider,
                model=outcome.model,
                prompt_version=self.EXTRACTION_PROMPT_VERSION,
                schema_version=self.EXTRACTION_SCHEMA_VERSION,
                # mode="json": JSONB persistence needs JSON-serializable values
                # (date/decimal become ISO strings); mode="python" raised
                # TypeError on document_date, killing the run after inference.
                extraction=outcome.extraction.model_dump(mode="json"),
            )
        )

    # ── Queries ─────────────────────────────────────────

    async def get_document(
        self,
        user_context: UserContext,
        document_id: UUID,
    ) -> DocumentWithExtraction | None:
        """Get a document with its latest extraction."""
        return await self._repo.get_document_with_extraction(
            user_id=user_context.user_id,
            document_id=document_id,
        )

    async def search_documents(
        self,
        user_context: UserContext,
        query: str | None = None,
    ) -> list[Document]:
        """Search documents for the user."""
        return await self._repo.search(
            user_id=user_context.user_id,
            query=query,
        )

    async def search_documents_semantically(
        self,
        user_context: UserContext,
        query: str,
        limit: int = 10,
    ) -> list[SemanticDocumentMatch]:
        """Find the user's completed semantic-index entries for a natural-language query."""
        if self._embedding_port is None or not query.strip():
            return []
        outcome = await self._embedding_port.embed(query[:self.MAX_INDEX_TEXT_CHARS])
        if outcome.status != "completed" or outcome.embedding is None:
            logger.warning(
                "Semantic document query embedding failed (status=%s, error_class=%s)",
                outcome.status,
                outcome.error_class,
            )
            return []
        return await self._repo.search_semantically(
            user_id=user_context.user_id,
            embedding=outcome.embedding,
            embedding_model=outcome.model,
            embedding_dimensions=len(outcome.embedding),
            limit=max(1, min(limit, 20)),
        )

    async def reindex_document_for_semantic_retrieval(
        self,
        user_context: UserContext,
        document_id: UUID,
    ) -> bool:
        """Explicitly rebuild one user-owned document's semantic index.

        This is an operator-facing recovery primitive, not an Agent capability:
        ownership is revalidated from trusted context and the existing document
        and latest extraction are reused without reading the stored file.
        """
        document = await self._repo.get_document_with_extraction(
            user_id=user_context.user_id,
            document_id=document_id,
        )
        if document is None:
            return False
        await self._index_for_semantic_retrieval(document.document, document.extraction)
        return True

    async def _index_for_semantic_retrieval(
        self,
        document: Document,
        extraction: AIExtraction | None,
    ) -> None:
        """Best-effort indexing: archival success never depends on embeddings."""
        if self._embedding_port is None:
            return
        index_text = self._build_index_text(document, extraction)
        outcome = await self._embedding_port.embed(index_text)
        status = "completed" if outcome.status == "completed" and outcome.embedding else "failed"
        try:
            await self._repo.upsert_search_chunk(
                DocumentSearchChunkUpsert(
                    document_id=document.id,
                    user_id=document.user_id,
                    extraction_id=extraction.id if extraction else None,
                    content_hash=sha256(index_text.encode("utf-8")).hexdigest(),
                    index_text=index_text,
                    embedding=outcome.embedding if status == "completed" else None,
                    embedding_provider=outcome.provider or None,
                    embedding_model=outcome.model or "unavailable",
                    embedding_dimensions=len(outcome.embedding) if outcome.embedding else 1536,
                    status=status,
                    error_class=outcome.error_class,
                )
            )
        except SQLAlchemyError:
            logger.warning("Document semantic-index persistence failed", exc_info=True)
            get_telemetry().counter(
                "ancora.document.semantic_index",
                attributes={"ancora.document.index_status": "persistence_failed"},
            )
            return
        get_telemetry().counter(
            "ancora.document.semantic_index",
            attributes={"ancora.document.index_status": status},
        )

    @classmethod
    def _build_index_text(cls, document: Document, extraction: AIExtraction | None) -> str:
        """Build bounded deterministic embedding input from untrusted metadata as data."""
        source: dict[str, object] = {
            "index_version": cls.INDEX_TEXT_VERSION,
            "filename": document.original_filename[:255],
            "mime_type": document.mime_type[:127],
        }
        if extraction is not None:
            fields: dict[str, object] = {}
            for key in ("document_type", "title", "summary", "entities", "dates", "amounts"):
                value = extraction.extraction.get(key)
                if value is not None:
                    fields[key] = cls._bounded_index_value(value)
            if fields:
                source["extraction"] = fields
        return json.dumps(source, ensure_ascii=False, sort_keys=True)[: cls.MAX_INDEX_TEXT_CHARS]

    @classmethod
    def _bounded_index_value(cls, value: object, *, depth: int = 0) -> object:
        """Preserve only bounded JSON-like untrusted data for retrieval indexing."""
        if depth >= 3:
            return "[truncated]"
        if isinstance(value, str):
            return value[:1000]
        if isinstance(value, (int, float, bool)) or value is None:
            return value
        if isinstance(value, list):
            return [cls._bounded_index_value(item, depth=depth + 1) for item in value[:20]]
        if isinstance(value, dict):
            return {
                str(key)[:80]: cls._bounded_index_value(item, depth=depth + 1)
                for key, item in list(value.items())[:20]
            }
        return str(value)[:1000]

    async def delete_document(
        self,
        user_context: UserContext,
        document_id: UUID,
    ) -> bool:
        """Delete a document and its physical file."""
        doc = await self._repo.get_by_id(user_context.user_id, document_id)
        if not doc:
            return False

        deleted = await self._repo.delete(user_context.user_id, document_id)
        if deleted:
            await self._storage.delete(doc.storage_key)
        return deleted

    @staticmethod
    def _build_extraction_prompt(
        doc: Document,
        content: bytes,
        *,
        visual_pages_attached: bool = False,
        extracted_text: str | None = None,
    ) -> str:
        """Serialize bounded, untrusted document metadata and preview as data.

        Instructions live in the extraction skill prompt, not alongside the
        untrusted text. JSON escaping avoids raw delimiter/newline breakouts;
        the model must still be treated as untrusted for authorization.
        """
        text_preview = ""
        if extracted_text is not None:
            # Deterministically extracted PDF text (specs/021 T2): same
            # untrusted-preview treatment as text/* content below.
            text_preview = extracted_text.encode("utf-8")[
                : DocumentService.MAX_TEXT_PREVIEW_BYTES
            ].decode("utf-8", errors="replace")
        elif doc.mime_type.startswith("text/") or doc.mime_type in {
            "application/json",
        }:
            text_preview = content[: DocumentService.MAX_TEXT_PREVIEW_BYTES].decode(
                "utf-8", errors="replace"
            )
        payload = {
            "source": {
                "filename": doc.original_filename[:255],
                "mime_type": doc.mime_type[:127],
                "size_bytes": doc.size_bytes,
                "text_preview": text_preview if text_preview else None,
                "visual_pages_attached": visual_pages_attached,
            },
            "target_schema": GenericDocumentExtraction.model_json_schema(),
        }
        # JSON quoting also bounds the filename to one field. Escape markup
        # characters in the serialized form to prevent literal closing tags
        # from resembling a trusted boundary in downstream prompt composition.
        return (
            json.dumps(payload, ensure_ascii=True)
            .replace("<", "\\u003c")
            .replace(">", "\\u003e")
            .replace("&", "\\u0026")
        )
