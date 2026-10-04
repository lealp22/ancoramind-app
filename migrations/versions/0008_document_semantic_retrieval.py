"""Add pgvector-backed document semantic retrieval (specs/026).

Revision ID: 0008_document_semantic_retrieval
Revises: 0007_recurrence_snooze
Create Date: 2026-10-04
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0008_document_semantic_retrieval"
down_revision: str | None = "0007_recurrence_snooze"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("""
        CREATE TABLE IF NOT EXISTS ancora.document_search_chunks (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            document_id UUID NOT NULL REFERENCES ancora.documents(id) ON DELETE CASCADE,
            user_id VARCHAR(255) NOT NULL,
            extraction_id UUID REFERENCES ancora.ai_extractions(id) ON DELETE SET NULL,
            chunk_index INT NOT NULL DEFAULT 0,
            content_hash VARCHAR(64) NOT NULL,
            index_text TEXT NOT NULL,
            embedding vector(1536),
            embedding_provider VARCHAR(63),
            embedding_model VARCHAR(255) NOT NULL,
            embedding_dimensions INT NOT NULL DEFAULT 1536,
            status VARCHAR(31) NOT NULL DEFAULT 'pending',
            error_class VARCHAR(127),
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_document_search_chunk_version
                UNIQUE (document_id, chunk_index, embedding_model, embedding_dimensions),
            CONSTRAINT chk_document_search_chunk_status
                CHECK (status IN ('pending', 'completed', 'failed'))
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_document_search_chunks_user_model_status
        ON ancora.document_search_chunks(user_id, embedding_model, embedding_dimensions)
        WHERE status = 'completed'
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_document_search_chunks_embedding_cosine
        ON ancora.document_search_chunks USING hnsw (embedding vector_cosine_ops)
        WHERE status = 'completed' AND embedding IS NOT NULL
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS ancora.document_search_chunks")
    # The extension may be shared by future migrations or external schema users.
    # Deliberately leave it installed on downgrade.
