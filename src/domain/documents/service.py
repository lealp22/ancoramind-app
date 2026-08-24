"""Document domain service — ingestion, storage, extraction, and search.

Framework-independent. Pipeline orchestration for the document lifecycle.
"""

import json
from uuid import UUID

from agno.models.openai import OpenAIChat

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
from src.storage.base import DocumentStorage, StoredDocument


class DocumentService:
    """Service for managing the document lifecycle."""

    EXTRACTION_PROMPT_VERSION = "1.0"
    EXTRACTION_SCHEMA_VERSION = "1.0"

    def __init__(
        self,
        repository: DocumentsRepository,
        storage: DocumentStorage,
        model: OpenAIChat,
        provider: str = "openai",
    ):
        self._repo = repository
        self._storage = storage
        self._model = model
        self._provider = provider

    @property
    def model_id(self) -> str:
        return self._model.id

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
        """Run AI extraction on a document.

        Currently handles text-based documents. Images/PDFs require
        multimodal model support (future enhancement).
        """
        # For now, extract based on filename + metadata
        # Full OCR/vision will be added when multimodal model is available
        extraction_result = await self._run_extraction(
            document=doc,
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

        if extraction_result is None:
            return None

        extraction_data = extraction_result.model_dump()

        return await self._repo.create_extraction(
            AIExtractionCreate(
                document_id=doc.id,
                provider=self._provider,
                model=self.model_id,
                prompt_version=self.EXTRACTION_PROMPT_VERSION,
                schema_version=self.EXTRACTION_SCHEMA_VERSION,
                extraction=extraction_data,
            )
        )

    async def _run_extraction(
        self,
        document: Document,
        prompt: str,
        schema: type,
    ) -> GenericDocumentExtraction | None:
        """Run an AI extraction using the agent's model with structured output."""
        try:
            from agno.agent import Agent

            agent = Agent(
                model=self._model,
                output_schema=schema,
                instructions=[
                    "Extract structured information from the document description.",
                    "Be precise. Use null for unknown fields.",
                ],
                markdown=False,
            )

            response = await agent.arun(prompt)
            if response and response.content:
                if isinstance(response.content, schema):
                    return response.content
                # Handle dict response
                return schema(**response.content)
        except Exception:
            pass
        return None

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