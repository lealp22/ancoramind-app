"""Document domain service — ingestion, storage, extraction, and search.

Framework-independent. Pipeline orchestration for the document lifecycle.
Extraction inference goes through the domain-owned ``DocumentExtractionPort``
(specs/013 T9); no runtime framework is imported here.
"""

import logging
from uuid import UUID

from src.domain.documents.extraction import DocumentExtractionPort
from src.domain.documents.models import (
    AIExtraction,
    AIExtractionCreate,
    Document,
    DocumentCreate,
    DocumentWithExtraction,
)
from src.domain.documents.schemas import GenericDocumentExtraction
from src.repositories.documents import DocumentsRepository
from src.security.user_context import UserContext
from src.storage.base import DocumentStorage

logger = logging.getLogger(__name__)


class DocumentService:
    """Service for managing the document lifecycle."""

    EXTRACTION_PROMPT_VERSION = "1.0"
    EXTRACTION_SCHEMA_VERSION = "1.0"

    def __init__(
        self,
        repository: DocumentsRepository,
        storage: DocumentStorage,
        extraction_port: DocumentExtractionPort,
    ) -> None:
        self._repo = repository
        self._storage = storage
        self._extraction_port = extraction_port

    # ── Pipeline ────────────────────────────────────────

    async def ingest(
        self,
        user_context: UserContext,
        content: bytes,
        filename: str,
        mime_type: str,
    ) -> DocumentWithExtraction:
        """Full document pipeline: store → register → extract.

        All steps are automatic per Architecture §17:
        receive, store, register metadata, analyze, save extraction.

        Returns:
            Document with its AI extraction.
        """
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
            ),
        )

        # 3. AI extraction (for text-based documents)
        extraction = await self._extract(doc)

        return DocumentWithExtraction(document=doc, extraction=extraction)

    async def _extract(self, doc: Document) -> AIExtraction | None:
        """Run AI extraction through the governed port.

        Currently handles text-based documents. Images/PDFs require
        multimodal model support (future enhancement).
        """
        outcome = await self._extraction_port.extract(
            prompt=(
                f"Analyze this document metadata:\n"
                f"Filename: {doc.original_filename}\n"
                f"Type: {doc.mime_type}\n"
                f"Size: {doc.size_bytes} bytes\n\n"
                f"Based on the filename and type, provide a best-effort "
                f"analysis of what this document likely contains."
            ),
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
                extraction=outcome.extraction.model_dump(),
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
