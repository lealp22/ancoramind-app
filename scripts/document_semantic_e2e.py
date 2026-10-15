"""Run one bounded production semantic-retrieval recovery/E2E check.

This operator script performs exactly three governed embedding calls: one
explicit reindex of an existing failed chunk and the same semantic query for
its owner and for a synthetic non-owner. It prints metadata-only evidence and
never prints index text, query text, vectors, document names, IDs, or secrets.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any
from uuid import UUID

from sqlalchemy import text

from src.agent.document_embeddings import GovernedDocumentEmbeddingAdapter
from src.config import Settings
from src.domain.documents.service import DocumentService
from src.repositories.database import close_database, get_session, init_database
from src.repositories.documents import DocumentsRepository
from src.security.user_context import UserContext
from src.storage.base import DocumentStorage, StoredDocument


class _UnusedStorage(DocumentStorage):
    async def store(
        self, content: bytes, filename: str, mime_type: str
    ) -> StoredDocument:  # pragma: no cover
        raise RuntimeError("storage_not_used")

    async def get(self, storage_key: str) -> bytes:  # pragma: no cover
        raise RuntimeError("storage_not_used")

    async def delete(self, storage_key: str) -> None:  # pragma: no cover
        raise RuntimeError("storage_not_used")

    async def exists(self, storage_key: str) -> bool:  # pragma: no cover
        raise RuntimeError("storage_not_used")


class _UnusedExtraction:
    async def extract(self, **kwargs: Any) -> Any:  # pragma: no cover
        raise RuntimeError("extraction_not_used")


async def _main() -> int:
    settings = Settings()
    if not settings.ancora_database_url:
        print("e2e_ok=false")
        print("reason=database_url_unavailable")
        return 1
    if not settings.litellm_proxy_enabled:
        print("e2e_ok=false")
        print("reason=proxy_disabled")
        return 1

    init_database(settings.ancora_database_url)
    session = await get_session()
    started = time.perf_counter()
    try:
        row = (
            await session.execute(
                text("""
                    SELECT c.document_id, c.user_id, c.index_text
                    FROM ancora.document_search_chunks c
                    JOIN ancora.documents d
                      ON d.id = c.document_id AND d.user_id = c.user_id
                    WHERE c.status = 'failed'
                      AND c.error_class = 'EmbeddingRouteUnavailable'
                    ORDER BY c.updated_at ASC
                    LIMIT 1
                """)
            )
        ).mappings().one_or_none()
        if row is None:
            print("e2e_ok=false")
            print("reason=failed_chunk_not_found")
            return 1

        document_id = UUID(str(row["document_id"]))
        owner = UserContext(user_id=str(row["user_id"]))
        # Reuse already-persisted bounded index data as the synthetic E2E query;
        # never print it or send raw document content.
        query = str(row["index_text"])
        service = DocumentService(
            repository=DocumentsRepository(session),
            storage=_UnusedStorage(),
            extraction_port=_UnusedExtraction(),
            embedding_port=GovernedDocumentEmbeddingAdapter(settings),
        )

        reindexed = await service.reindex_document_for_semantic_retrieval(owner, document_id)
        owner_matches = await service.search_documents_semantically(owner, query, limit=20)
        outsider_matches = await service.search_documents_semantically(
            UserContext(user_id="operator-e2e-isolation-non-owner"),
            query,
            limit=20,
        )
        owner_found = any(match.document.id == document_id for match in owner_matches)
        outsider_leak = any(match.document.id == document_id for match in outsider_matches)
        stored = (
            await session.execute(
                text("""
                    SELECT status, embedding_model, embedding_dimensions,
                           embedding IS NOT NULL AS has_embedding, error_class
                    FROM ancora.document_search_chunks
                    WHERE document_id = :document_id
                      AND embedding_model = 'ancoramind-embeddings-r1'
                      AND embedding_dimensions = 1536
                    ORDER BY updated_at DESC
                    LIMIT 1
                """),
                {"document_id": document_id},
            )
        ).mappings().one_or_none()
        persisted = bool(
            stored
            and stored["status"] == "completed"
            and stored["has_embedding"]
            and stored["error_class"] is None
        )
        e2e_ok = reindexed and persisted and owner_found and not outsider_leak
        print(f"e2e_ok={str(e2e_ok).lower()}")
        print("embedding_calls=3")
        print(f"reindex_ok={str(reindexed and persisted).lower()}")
        print(f"owner_search_found={str(owner_found).lower()}")
        print(f"non_owner_isolated={str(not outsider_leak).lower()}")
        print("embedding_model=ancoramind-embeddings-r1")
        print("dimensions=1536")
        print(f"latency_ms={round((time.perf_counter() - started) * 1000)}")
        return 0 if e2e_ok else 1
    except Exception as exc:
        print("e2e_ok=false")
        print(f"reason={type(exc).__name__}")
        return 1
    finally:
        await session.close()
        await close_database()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
