"""Add consent_mode to action proposals for the WRITE_TRIVIAL tier (specs/035, BL-46).

Revision ID: 0014_write_trivial_consent_mode
Revises: 0013_session_token_index
Create Date: 2026-10-13

``consent_mode`` distinguishes how a proposal's execution was authorised:

* ``explicit_confirmation`` (default): the existing WRITE_REVIEWABLE path —
  a user "Sí" claimed via ``claim_confirmation`` before ``ProposalExecutor``
  ran it. Unchanged by this revision.
* ``self_authorized``: the new WRITE_TRIVIAL path (``TrivialExecutor``) —
  the mutation already ran because the user's own request was the signal
  (same precedent as ``analyze_document``, specs/023 T4.7); the row is
  inserted directly in a terminal ``executed`` state, never
  ``pending_confirmation``, with ``confirming_interaction_id`` left NULL
  (that column's unique index is partial on NOT NULL, so this never
  collides with a real confirmation).
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0014_write_trivial_consent_mode"
down_revision: str | None = "0013_session_token_index"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CONSENT_MODES = "'explicit_confirmation', 'self_authorized'"


def upgrade() -> None:
    """Add the column and its CHECK, idempotently."""
    op.execute(
        "ALTER TABLE ancora.action_proposals "
        "ADD COLUMN IF NOT EXISTS consent_mode VARCHAR(32) "
        "NOT NULL DEFAULT 'explicit_confirmation'"
    )
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint c
                JOIN pg_namespace n ON n.oid = c.connamespace
                WHERE n.nspname = 'ancora'
                  AND c.conname = 'ck_action_proposals_consent_mode'
            ) THEN
                ALTER TABLE ancora.action_proposals
                ADD CONSTRAINT ck_action_proposals_consent_mode
                CHECK (consent_mode IN (""" + CONSENT_MODES + """));
            END IF;
        END $$
    """)


def downgrade() -> None:
    """Drop the CHECK and the column.

    No rows to fold back: pre-existing proposals keep their implicit
    ``explicit_confirmation`` behaviour either way, since nothing read
    ``consent_mode`` before this revision.
    """
    op.execute(
        "ALTER TABLE ancora.action_proposals "
        "DROP CONSTRAINT IF EXISTS ck_action_proposals_consent_mode"
    )
    op.execute("ALTER TABLE ancora.action_proposals DROP COLUMN IF EXISTS consent_mode")
