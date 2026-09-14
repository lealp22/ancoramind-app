"""Unit tests for the T9 DocumentExtractionPort and DocumentService wiring."""

from __future__ import annotations

import inspect
import logging
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

import src.domain.documents.service as service_module
from src.domain.documents.extraction import DocumentExtractionOutcome
from src.domain.documents.models import AIExtraction, Document
from src.domain.documents.schemas import GenericDocumentExtraction
from src.domain.documents.service import DocumentService
from src.repositories.documents import DocumentsRepository
from src.security.user_context import UserContext
from src.storage.base import DocumentStorage, StoredDocument


class _FakeExtractionPort:
    def __init__(self, outcome):
        self._outcome = outcome
        self.calls: list[tuple[str, type]] = []

    async def extract(self, prompt, schema):
        self.calls.append((prompt, schema))
        return self._outcome


def _user() -> UserContext:
    return UserContext(user_id="test-user")


def _service(port, repo) -> DocumentService:
    storage = AsyncMock(spec=DocumentStorage)
    storage.store.return_value = StoredDocument(
        storage_key="2026/09/factura.pdf",
        original_filename="factura.pdf",
        mime_type="application/pdf",
        size_bytes=9,
    )
    return DocumentService(repository=repo, storage=storage, extraction_port=port)


def _repo_returning(document: Document) -> AsyncMock:
    repo = AsyncMock(spec=DocumentsRepository)
    repo.create.return_value = document
    repo.create_extraction.return_value = AIExtraction(
        id=uuid4(),
        document_id=document.id,
        provider="openrouter",
        model="test/model",
        prompt_version="1.0",
        schema_version="1.0",
        extraction={"document_type": "invoice"},
        confidence=0.8,
        created_at=datetime.now(tz=UTC),
    )
    return repo


def _document() -> Document:
    return Document(
        id=uuid4(),
        user_id="test-user",
        storage_key="2026/09/factura.pdf",
        original_filename="factura.pdf",
        mime_type="application/pdf",
        size_bytes=9,
        created_at=datetime.now(tz=UTC),
    )


def test_document_service_module_has_no_runtime_framework_imports() -> None:
    """T9: the documents domain must not depend on Agno anymore."""
    source = inspect.getsource(service_module)

    assert "agno" not in source
    assert "except Exception" not in source


async def test_ingest_persists_extraction_with_real_provider_and_model() -> None:
    document = _document()
    repo = _repo_returning(document)
    port = _FakeExtractionPort(
        DocumentExtractionOutcome(
            extraction=GenericDocumentExtraction(
                document_type="invoice",
                summary="Factura de taller",
                confidence=0.8,
            ),
            provider="OpenRouter",
            model="test/model",
            status="completed",
        )
    )
    service = _service(port, repo)

    result = await service.ingest(_user(), b"%PDF-1.4", "factura.pdf", "application/pdf")

    assert result.extraction is repo.create_extraction.return_value
    prompt, schema = port.calls[0]
    assert schema is GenericDocumentExtraction
    assert "factura.pdf" in prompt
    create_data = repo.create_extraction.await_args.args[0]
    assert create_data.provider == "OpenRouter"
    assert create_data.model == "test/model"
    assert create_data.prompt_version == DocumentService.EXTRACTION_PROMPT_VERSION
    assert create_data.extraction["document_type"] == "invoice"


async def test_ingest_without_extraction_stays_archived_and_logs_metadata(
    caplog: pytest.LogCaptureFixture,
) -> None:
    document = _document()
    repo = _repo_returning(document)
    port = _FakeExtractionPort(
        DocumentExtractionOutcome(
            extraction=None,
            provider="OpenRouter",
            model="test/model",
            status="failed",
            error_class="ModelProviderError",
        )
    )
    service = _service(port, repo)

    with caplog.at_level(logging.WARNING, logger="src.domain.documents.service"):
        result = await service.ingest(_user(), b"%PDF-1.4", "factura.pdf", "application/pdf")

    assert result.document is document
    assert result.extraction is None
    repo.create_extraction.assert_not_awaited()
    failure_log = caplog.text
    assert "document_id=" in failure_log
    assert "ModelProviderError" in failure_log
    assert "factura" not in failure_log  # content-free failure metadata


async def test_ingest_propagates_governance_violations() -> None:
    class _ViolatingPort:
        async def extract(self, prompt, schema):  # pragma: no cover - raises
            raise RuntimeError("no governed frontier available")

    document = _document()
    repo = _repo_returning(document)
    service = _service(_ViolatingPort(), repo)

    with pytest.raises(RuntimeError, match="no governed frontier"):
        await service.ingest(_user(), b"%PDF-1.4", "factura.pdf", "application/pdf")

    repo.create_extraction.assert_not_awaited()


def test_outcome_is_immutable_and_content_free_by_contract() -> None:
    outcome = DocumentExtractionOutcome(
        extraction=None,
        provider="OpenRouter",
        model="test/model",
        status="failed",
        error_class="TimeoutError",
    )

    with pytest.raises(FrozenInstanceError):
        outcome.status = "completed"

    assert outcome.error_detail is None
