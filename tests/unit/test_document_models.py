"""Unit tests for Document domain models."""

from datetime import datetime, timezone
from uuid import uuid4

from src.domain.documents.models import (
    AIExtraction,
    Document,
    DocumentCreate,
    DocumentWithExtraction,
)


class TestDocumentCreate:
    def test_valid(self):
        dc = DocumentCreate(storage_key="2026/08/abc.pdf", original_filename="factura.pdf",
                           mime_type="application/pdf", size_bytes=1024)
        assert dc.storage_key == "2026/08/abc.pdf"
        assert dc.original_filename == "factura.pdf"

    def test_zero_size_allowed(self):
        dc = DocumentCreate(storage_key="k", original_filename="f", mime_type="text/plain", size_bytes=0)
        assert dc.size_bytes == 0


class TestDocument:
    def test_from_attributes(self):
        doc = Document(id=uuid4(), user_id="u1", storage_key="k", original_filename="f.pdf",
                       mime_type="application/pdf", size_bytes=100,
                       created_at=datetime.now(tz=timezone.utc))
        assert doc.user_id == "u1"
        assert doc.mime_type == "application/pdf"


class TestAIExtraction:
    def test_from_attributes(self):
        ext = AIExtraction(id=uuid4(), document_id=uuid4(), provider="openai", model="gpt-4o",
                          prompt_version="1.0", schema_version="1.0",
                          extraction={"type": "invoice"}, confidence=0.9,
                          created_at=datetime.now(tz=timezone.utc))
        assert ext.provider == "openai"
        assert ext.confidence == 0.9


class TestDocumentWithExtraction:
    def test_with_extraction(self):
        doc = Document(id=uuid4(), user_id="u1", storage_key="k", original_filename="f.pdf",
                       mime_type="application/pdf", size_bytes=100,
                       created_at=datetime.now(tz=timezone.utc))
        ext = AIExtraction(id=uuid4(), document_id=doc.id, provider="openai", model="gpt-4o",
                          prompt_version="1.0", schema_version="1.0",
                          extraction={}, confidence=None,
                          created_at=datetime.now(tz=timezone.utc))
        dwe = DocumentWithExtraction(document=doc, extraction=ext)
        assert dwe.document.id == doc.id
        assert dwe.extraction is not None

    def test_without_extraction(self):
        doc = Document(id=uuid4(), user_id="u1", storage_key="k", original_filename="f.pdf",
                       mime_type="application/pdf", size_bytes=100,
                       created_at=datetime.now(tz=timezone.utc))
        dwe = DocumentWithExtraction(document=doc, extraction=None)
        assert dwe.extraction is None