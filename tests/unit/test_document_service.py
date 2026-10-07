"""Unit tests for BL-31: per-user document deduplication by content hash."""

from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256
from unittest.mock import AsyncMock
from uuid import uuid4

from src.domain.documents.extraction import DocumentExtractionOutcome
from src.domain.documents.models import AIExtraction, Document, DocumentWithExtraction
from src.domain.documents.service import DocumentService
from src.repositories.documents import DocumentsRepository
from src.security.user_context import UserContext
from src.storage.base import DocumentStorage, StoredDocument


def _user() -> UserContext:
    return UserContext(user_id="test-user")


def _document(content_hash: str | None = None) -> Document:
    return Document(
        id=uuid4(),
        user_id="test-user",
        storage_key="2026/09/factura.pdf",
        original_filename="factura.pdf",
        mime_type="application/pdf",
        size_bytes=9,
        content_hash=content_hash,
        created_at=datetime.now(tz=UTC),
    )


def _service(repo: AsyncMock) -> DocumentService:
    storage = AsyncMock(spec=DocumentStorage)
    extraction_port = AsyncMock()
    return DocumentService(repository=repo, storage=storage, extraction_port=extraction_port)


async def test_duplicate_content_hash_reuses_existing_document_without_storing_or_extracting():
    content = b"same invoice bytes"
    content_hash = sha256(content).hexdigest()
    existing_doc = _document(content_hash=content_hash)
    existing_extraction = AIExtraction(
        id=uuid4(),
        document_id=existing_doc.id,
        provider="openrouter",
        model="test/model",
        prompt_version="1.0",
        schema_version="1.0",
        extraction={"document_type": "invoice"},
        confidence=0.8,
        created_at=datetime.now(tz=UTC),
    )

    repo = AsyncMock(spec=DocumentsRepository)
    repo.get_by_content_hash.return_value = existing_doc
    repo.get_document_with_extraction.return_value = DocumentWithExtraction(
        document=existing_doc, extraction=existing_extraction
    )
    service = _service(repo)

    result = await service.ingest(_user(), content, "factura.pdf", "application/pdf")

    assert result.document.id == existing_doc.id
    assert result.extraction is existing_extraction
    repo.get_by_content_hash.assert_awaited_once_with(
        user_id="test-user", content_hash=content_hash
    )
    repo.get_document_with_extraction.assert_awaited_once_with(
        user_id="test-user", document_id=existing_doc.id
    )
    service._storage.store.assert_not_called()
    repo.create.assert_not_called()
    service._extraction_port.extract.assert_not_called()


async def test_new_content_hash_stores_and_extracts_passing_hash_to_create():
    content = b"a brand new invoice"
    content_hash = sha256(content).hexdigest()
    new_doc = _document(content_hash=content_hash)

    repo = AsyncMock(spec=DocumentsRepository)
    repo.get_by_content_hash.return_value = None
    repo.create.return_value = new_doc
    repo.create_extraction.return_value = AIExtraction(
        id=uuid4(),
        document_id=new_doc.id,
        provider="openrouter",
        model="test/model",
        prompt_version="1.0",
        schema_version="1.0",
        extraction={"document_type": "invoice"},
        confidence=0.8,
        created_at=datetime.now(tz=UTC),
    )
    service = _service(repo)
    service._storage.store.return_value = StoredDocument(
        storage_key="2026/09/factura.pdf",
        original_filename="factura.pdf",
        mime_type="application/pdf",
        size_bytes=len(content),
    )
    service._extraction_port.extract.return_value = DocumentExtractionOutcome(
        extraction=None, provider="test", model="test", status="failed"
    )

    await service.ingest(_user(), content, "factura.pdf", "application/pdf")

    service._storage.store.assert_awaited_once()
    created = repo.create.await_args.kwargs["data"]
    assert created.content_hash == content_hash
    repo.get_document_with_extraction.assert_not_called()
