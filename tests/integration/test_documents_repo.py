"""Integration tests for DocumentsRepository against real PostgreSQL (specs/009)."""

from hashlib import sha256
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from src.domain.documents.models import (
    AIExtractionCreate,
    DocumentCreate,
    DocumentSearchChunkUpsert,
)
from src.repositories.documents import DocumentsRepository

pytestmark = pytest.mark.integration


def _document(filename: str = "factura-taller.pdf", content: bytes | None = None) -> DocumentCreate:
    return DocumentCreate(
        storage_key=f"2026/09/{filename}",
        original_filename=filename,
        mime_type="application/pdf",
        size_bytes=2048,
        content_hash=sha256(content if content is not None else filename.encode()).hexdigest(),
    )


async def test_document_lifecycle_is_user_scoped(session, user_a, user_b):
    repo = DocumentsRepository(session)

    doc = await repo.create(user_a, _document())
    assert doc.id is not None
    assert doc.created_at.tzinfo is not None

    fetched = await repo.get_by_id(user_a, doc.id)
    assert fetched is not None
    assert fetched.original_filename == "factura-taller.pdf"

    # Other users cannot see or delete it
    assert await repo.get_by_id(user_b, doc.id) is None
    assert await repo.delete(user_b, doc.id) is False

    # ILIKE search by filename
    assert len(await repo.search(user_a, "TALLER")) == 1
    assert await repo.search(user_b, "taller") == []

    assert await repo.delete(user_a, doc.id) is True
    assert await repo.get_by_id(user_a, doc.id) is None
    assert await repo.delete(user_a, doc.id) is False  # second delete: no-op


async def test_extractions_latest_wins_and_cascade(session, user_a):
    repo = DocumentsRepository(session)

    doc = await repo.create(user_a, _document("presupuesto.pdf"))
    first = await repo.create_extraction(
        AIExtractionCreate(
            document_id=doc.id,
            provider="openai",
            model="gpt-5.4-mini",
            prompt_version="1.0",
            schema_version="1.0",
            extraction={"document_type": "invoice", "confidence": 0.6},
        )
    )
    assert first.confidence == 0.6
    assert first.extraction == {"document_type": "invoice", "confidence": 0.6}

    await repo.create_extraction(
        AIExtractionCreate(
            document_id=doc.id,
            provider="openai",
            model="gpt-5.4-mini",
            prompt_version="1.0",
            schema_version="1.0",
            extraction={"document_type": "invoice", "summary": "v2", "confidence": 0.9},
        )
    )

    latest = await repo.get_latest_extraction(doc.id)
    assert latest is not None
    assert latest.extraction["summary"] == "v2"

    combined = await repo.get_document_with_extraction(user_a, doc.id)
    assert combined is not None
    assert combined.extraction.id == latest.id

    # ON DELETE CASCADE: deleting the document removes its extractions
    assert await repo.delete(user_a, doc.id) is True
    assert await repo.get_latest_extraction(doc.id) is None


async def test_get_with_extraction_of_missing_document(session, user_a):
    repo = DocumentsRepository(session)

    assert await repo.get_by_id(user_a, uuid4()) is None
    assert await repo.get_document_with_extraction(user_a, uuid4()) is None


async def test_semantic_search_is_user_scoped_idempotent_and_cascades(session, user_a, user_b):
    repo = DocumentsRepository(session)
    own = await repo.create(user_a, _document("contrato-murcia.pdf"))
    other = await repo.create(user_b, _document("contrato-privado.pdf"))
    vector = (0.1,) * 1536

    own_chunk = DocumentSearchChunkUpsert(
        document_id=own.id,
        user_id=user_a,
        content_hash="a" * 64,
        index_text='{"filename":"contrato-murcia.pdf"}',
        embedding=vector,
        embedding_provider="test",
        embedding_model="test-embedding-r1",
        embedding_dimensions=1536,
        status="completed",
    )
    await repo.upsert_search_chunk(own_chunk)
    await repo.upsert_search_chunk(own_chunk.model_copy(update={"content_hash": "b" * 64}))
    await repo.upsert_search_chunk(
        own_chunk.model_copy(update={"document_id": other.id, "user_id": user_b})
    )

    own_matches = await repo.search_semantically(
        user_id=user_a,
        embedding=vector,
        embedding_model="test-embedding-r1",
        embedding_dimensions=1536,
    )
    assert [match.document.id for match in own_matches] == [own.id]
    assert await repo.search_semantically(
        user_id=user_b,
        embedding=vector,
        embedding_model="test-embedding-r1",
        embedding_dimensions=1536,
    ) == [own_matches[0].model_copy(update={"document": other})]

    assert await repo.delete(user_a, own.id) is True
    assert await repo.search_semantically(
        user_id=user_a,
        embedding=vector,
        embedding_model="test-embedding-r1",
        embedding_dimensions=1536,
    ) == []


async def test_get_by_content_hash_returns_existing_within_user(session, user_a):
    repo = DocumentsRepository(session)
    content_hash = sha256(b"same bytes twice").hexdigest()
    created = await repo.create(
        user_a,
        DocumentCreate(
            storage_key="2026/09/original.pdf",
            original_filename="original.pdf",
            mime_type="application/pdf",
            size_bytes=10,
            content_hash=content_hash,
        ),
    )

    found = await repo.get_by_content_hash(user_a, content_hash)
    assert found is not None
    assert found.id == created.id

    assert await repo.get_by_content_hash(user_a, sha256(b"never stored").hexdigest()) is None


async def test_duplicate_content_hash_rejected_by_unique_index(session, user_a):
    repo = DocumentsRepository(session)
    content_hash = sha256(b"duplicate upload").hexdigest()
    await repo.create(
        user_a,
        DocumentCreate(
            storage_key="2026/09/first.pdf",
            original_filename="first.pdf",
            mime_type="application/pdf",
            size_bytes=10,
            content_hash=content_hash,
        ),
    )

    with pytest.raises(IntegrityError):
        await repo.create(
            user_a,
            DocumentCreate(
                storage_key="2026/09/second.pdf",
                original_filename="second.pdf",
                mime_type="application/pdf",
                size_bytes=10,
                content_hash=content_hash,
            ),
        )


async def test_same_content_hash_different_users_both_stored(session, user_a, user_b):
    repo = DocumentsRepository(session)
    content_hash = sha256(b"shared file content").hexdigest()

    own = await repo.create(
        user_a,
        DocumentCreate(
            storage_key="2026/09/shared-a.pdf",
            original_filename="shared-a.pdf",
            mime_type="application/pdf",
            size_bytes=10,
            content_hash=content_hash,
        ),
    )
    other = await repo.create(
        user_b,
        DocumentCreate(
            storage_key="2026/09/shared-b.pdf",
            original_filename="shared-b.pdf",
            mime_type="application/pdf",
            size_bytes=10,
            content_hash=content_hash,
        ),
    )

    assert own.id != other.id
    assert (await repo.get_by_content_hash(user_a, content_hash)).id == own.id
    assert (await repo.get_by_content_hash(user_b, content_hash)).id == other.id
