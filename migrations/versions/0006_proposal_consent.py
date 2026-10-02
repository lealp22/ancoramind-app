"""Add durable consent evidence to action proposals (specs/023 T4.1, specs/022).

Revision ID: 0006_proposal_consent
Revises: 0005_telegram_pairing
Create Date: 2026-10-02

State model (``specs/022-llm-input-trust/consent-design.md``)::

    pending_confirmation -> confirmed -> executing -> executed
                                                   -> failed_definitive
                                                   -> failed_ambiguous
    pending_confirmation -> expired | discarded      (never executed)

``confirmed`` is consumed evidence bound to exactly one confirming interaction,
not a reusable licence. Proposals created before this revision carry no
provenance or payload hash: they stay in the table for audit but the Core
treats them as non-executable (a new proposal must be generated).
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0006_proposal_consent"
down_revision: str | None = "0005_telegram_pairing"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PROPOSAL_STATUSES = (
    "'pending_confirmation', 'confirmed', 'executing', 'executed', "
    "'failed_definitive', 'failed_ambiguous', 'expired', 'discarded'"
)


def upgrade() -> None:
    """Add consent/provenance columns, a state CHECK and single-use indexes."""
    columns = (
        "payload_hash VARCHAR(64)",
        "chat_id BIGINT",
        "bot_id BIGINT",
        "presented_at TIMESTAMPTZ",
        "presented_response_id UUID",
        "expires_at TIMESTAMPTZ",
        "confirming_interaction_id UUID",
        "executing_at TIMESTAMPTZ",
        "completed_at TIMESTAMPTZ",
        "failure_reason VARCHAR(127)",
    )
    for column in columns:
        op.execute(f"ALTER TABLE ancora.action_proposals ADD COLUMN IF NOT EXISTS {column}")

    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint c
                JOIN pg_namespace n ON n.oid = c.connamespace
                WHERE n.nspname = 'ancora'
                  AND c.conname = 'fk_action_proposals_presented_response'
            ) THEN
                ALTER TABLE ancora.action_proposals
                ADD CONSTRAINT fk_action_proposals_presented_response
                FOREIGN KEY (presented_response_id)
                REFERENCES ancora.logical_responses(id) ON DELETE SET NULL;
            END IF;
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint c
                JOIN pg_namespace n ON n.oid = c.connamespace
                WHERE n.nspname = 'ancora'
                  AND c.conname = 'fk_action_proposals_confirming_interaction'
            ) THEN
                ALTER TABLE ancora.action_proposals
                ADD CONSTRAINT fk_action_proposals_confirming_interaction
                FOREIGN KEY (confirming_interaction_id)
                REFERENCES ancora.telegram_interactions(id) ON DELETE RESTRICT;
            END IF;
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint c
                JOIN pg_namespace n ON n.oid = c.connamespace
                WHERE n.nspname = 'ancora'
                  AND c.conname = 'ck_action_proposals_status'
            ) THEN
                ALTER TABLE ancora.action_proposals
                ADD CONSTRAINT ck_action_proposals_status
                CHECK (status IN (""" + PROPOSAL_STATUSES + """));
            END IF;
        END $$
    """)

    # One confirming interaction can authorise at most one proposal.
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_action_proposals_confirming_interaction
        ON ancora.action_proposals(confirming_interaction_id)
        WHERE confirming_interaction_id IS NOT NULL
    """)
    # Pending-proposal lookup by principal, used by the pre-Agent consent check.
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_action_proposals_pending_principal
        ON ancora.action_proposals(user_id, bot_id, chat_id)
        WHERE status = 'pending_confirmation'
    """)


def downgrade() -> None:
    """Remove consent evidence; legacy statuses are folded back to the old model."""
    # Rows in states the previous model did not know must not break it.
    op.execute("""
        UPDATE ancora.action_proposals
        SET status = 'executed'
        WHERE status IN ('executing', 'failed_definitive', 'failed_ambiguous')
    """)
    op.execute("""
        UPDATE ancora.action_proposals
        SET status = 'pending_confirmation'
        WHERE status IN ('expired', 'discarded')
          AND confirmed_at IS NULL AND executed_at IS NULL
    """)
    op.execute("DROP INDEX IF EXISTS ancora.idx_action_proposals_pending_principal")
    op.execute("DROP INDEX IF EXISTS ancora.uq_action_proposals_confirming_interaction")
    for constraint in (
        "ck_action_proposals_status",
        "fk_action_proposals_confirming_interaction",
        "fk_action_proposals_presented_response",
    ):
        op.execute(f"ALTER TABLE ancora.action_proposals DROP CONSTRAINT IF EXISTS {constraint}")
    for column in (
        "failure_reason",
        "completed_at",
        "executing_at",
        "confirming_interaction_id",
        "expires_at",
        "presented_response_id",
        "presented_at",
        "bot_id",
        "chat_id",
        "payload_hash",
    ):
        op.execute(f"ALTER TABLE ancora.action_proposals DROP COLUMN IF EXISTS {column}")
