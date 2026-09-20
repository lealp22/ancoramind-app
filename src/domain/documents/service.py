"""Document domain service — ingestion, storage, extraction, and search.

Framework-independent. Pipeline orchestration for the document lifecycle.
Extraction inference goes through the domain-owned ``DocumentExtractionPort``
(specs/013 T9); no runtime framework is imported here.
"""

import json
import logging
from uuid import UUID

from src.domain.documents.extraction import DocumentExtractionPort, DocumentVisualPage
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

    EXTRACTION_PROMPT_VERSION = "1.1"
    EXTRACTION_SCHEMA_VERSION = "1.1"
    MAX_TEXT_PREVIEW_BYTES = 5000

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
        visual_pages: tuple[DocumentVisualPage, ...] = (),
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
        extraction = await self._extract(doc, content, visual_pages)

        return DocumentWithExtraction(document=doc, extraction=extraction)

    async def _extract(
        self,
        doc: Document,
        content: bytes,
        visual_pages: tuple[DocumentVisualPage, ...],
    ) -> AIExtraction | None:
        """Run AI extraction through the governed port.

        Visual pages are transient input from the infrastructure layer. They are
        never persisted in the extraction audit or exported to observability.
        """
        prompt = self._build_extraction_prompt(doc, content)
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
    def _build_extraction_prompt(doc: Document, content: bytes) -> str:
        """Build the v1.1 extraction prompt: metadata + content + target schema.

        The document content travels inside explicit DATA delimiters: it is
        untrusted data to be read, never instructions to be followed. The
        schema is embedded because ``response_format`` may not survive the
        full Gateway path; the instruction says "return only the JSON object".
        """
        text_preview = ""
        if doc.mime_type.startswith("text/") or doc.mime_type in {
            "application/json",
        }:
            text_preview = content[: DocumentService.MAX_TEXT_PREVIEW_BYTES].decode(
                "utf-8", errors="replace"
            )
        content_block = (
            f"<document_data>\n{text_preview}\n</document_data>"
            if text_preview
            else "(binary document; the attached pages/images contain the visual content)"
        )
        schema_json = json.dumps(
            GenericDocumentExtraction.model_json_schema(), ensure_ascii=False
        )
        return (
            f"Filename: {doc.original_filename}\n"
            f"Type: {doc.mime_type}\n"
            f"Size: {doc.size_bytes} bytes\n\n"
            f"{content_block}\n\n"
            "Extract the document information into exactly this JSON schema "
            "(return only the JSON object):\n"
            f"{schema_json}"
        )
