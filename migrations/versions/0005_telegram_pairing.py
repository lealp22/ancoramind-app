"""Add governed Telegram evaluator pairing tables.

Revision ID: 0005_telegram_pairing
Revises: 0004_ai_extractions_schema
Create Date: 2026-09-27
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0005_telegram_pairing"
down_revision: str | None = "0004_ai_extractions_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create auditable invitation, request and authorization records idempotently."""
    op.execute("""
        CREATE TABLE IF NOT EXISTS ancora.telegram_pairing_invitations (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            code_hash VARCHAR(128) NOT NULL UNIQUE,
            status VARCHAR(31) NOT NULL,
            max_uses INT NOT NULL CHECK (max_uses > 0),
            use_count INT NOT NULL DEFAULT 0 CHECK (use_count >= 0 AND use_count <= max_uses),
            expires_at TIMESTAMPTZ NOT NULL,
            created_by VARCHAR(255) NOT NULL,
            reason TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            revoked_by VARCHAR(255),
            revoked_reason TEXT,
            revoked_at TIMESTAMPTZ
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_pairing_invitations_active_expiry
        ON ancora.telegram_pairing_invitations(expires_at) WHERE status = 'active'
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS ancora.telegram_pairing_requests (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            invitation_id UUID NOT NULL
                REFERENCES ancora.telegram_pairing_invitations(id) ON DELETE RESTRICT,
            telegram_user_id BIGINT NOT NULL,
            status VARCHAR(31) NOT NULL,
            requested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            decided_by VARCHAR(255),
            decision_reason TEXT,
            decided_at TIMESTAMPTZ,
            CONSTRAINT uq_pairing_request_invitation_user UNIQUE (invitation_id, telegram_user_id)
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_pairing_requests_pending
        ON ancora.telegram_pairing_requests(requested_at) WHERE status = 'pending'
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS ancora.telegram_pairing_authorizations (
            telegram_user_id BIGINT PRIMARY KEY,
            request_id UUID NOT NULL
                REFERENCES ancora.telegram_pairing_requests(id) ON DELETE RESTRICT,
            status VARCHAR(31) NOT NULL,
            authorized_by VARCHAR(255) NOT NULL,
            reason TEXT NOT NULL,
            authorized_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            revoked_by VARCHAR(255),
            revoked_reason TEXT,
            revoked_at TIMESTAMPTZ
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_pairing_authorizations_active
        ON ancora.telegram_pairing_authorizations(telegram_user_id) WHERE status = 'active'
    """)


def downgrade() -> None:
    """Remove pairing tables without altering the Telegram interaction ledger."""
    op.execute("DROP TABLE IF EXISTS ancora.telegram_pairing_authorizations CASCADE")
    op.execute("DROP TABLE IF EXISTS ancora.telegram_pairing_requests CASCADE")
    op.execute("DROP TABLE IF EXISTS ancora.telegram_pairing_invitations CASCADE")
