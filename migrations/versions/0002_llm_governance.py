"""Add governed LLM access, Telegram ledger and runtime configuration tables.

Revision ID: 0002_llm_governance
Revises: 0001_ancora_baseline
Create Date: 2026-09-13
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0002_llm_governance"
down_revision: str | None = "0001_ancora_baseline"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add specs/013 schema idempotently without changing existing rows."""
    op.execute("""
        CREATE TABLE IF NOT EXISTS ancora.runtime_config_revisions (
            revision BIGSERIAL PRIMARY KEY,
            schema_version INT NOT NULL,
            config JSONB NOT NULL,
            checksum VARCHAR(128) NOT NULL,
            validation_status VARCHAR(31) NOT NULL,
            validation_errors JSONB NOT NULL DEFAULT '[]',
            created_by VARCHAR(255) NOT NULL,
            reason TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_runtime_config_created_at ON ancora.runtime_config_revisions(created_at DESC)"
    )

    op.execute("""
        CREATE TABLE IF NOT EXISTS ancora.runtime_config_active (
            singleton_id BOOLEAN PRIMARY KEY DEFAULT TRUE CHECK (singleton_id),
            active_revision BIGINT NOT NULL REFERENCES ancora.runtime_config_revisions(revision) ON DELETE RESTRICT,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS ancora.runtime_config_activations (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            revision BIGINT NOT NULL REFERENCES ancora.runtime_config_revisions(revision) ON DELETE RESTRICT,
            previous_revision BIGINT REFERENCES ancora.runtime_config_revisions(revision) ON DELETE RESTRICT,
            actor VARCHAR(255) NOT NULL,
            reason TEXT NOT NULL,
            activated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_runtime_config_activations_revision ON ancora.runtime_config_activations(revision)"
    )

    op.execute("""
        CREATE TABLE IF NOT EXISTS ancora.telegram_interactions (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            bot_id BIGINT NOT NULL,
            telegram_update_id BIGINT NOT NULL,
            telegram_message_id BIGINT,
            chat_id BIGINT,
            telegram_user_id BIGINT,
            update_type VARCHAR(63) NOT NULL,
            status VARCHAR(31) NOT NULL,
            payload_ciphertext BYTEA,
            payload_key_version INT,
            payload_fingerprint VARCHAR(128),
            config_revision BIGINT REFERENCES ancora.runtime_config_revisions(revision) ON DELETE RESTRICT,
            agno_session_id VARCHAR(255),
            agno_run_id VARCHAR(255),
            model_call_count INT NOT NULL DEFAULT 0,
            gateway_request_count INT NOT NULL DEFAULT 0,
            tool_call_count INT NOT NULL DEFAULT 0,
            estimated_cost NUMERIC(18, 8),
            actual_cost NUMERIC(18, 8),
            error_class VARCHAR(127),
            error_detail_code VARCHAR(127),
            received_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            accepted_at TIMESTAMPTZ,
            agent_started_at TIMESTAMPTZ,
            response_ready_at TIMESTAMPTZ,
            delivery_started_at TIMESTAMPTZ,
            completed_at TIMESTAMPTZ,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_telegram_interactions_bot_update UNIQUE (bot_id, telegram_update_id),
            CONSTRAINT uq_telegram_interactions_agno_run UNIQUE (agno_run_id)
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_telegram_interactions_status ON ancora.telegram_interactions(status)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_telegram_interactions_chat_status ON ancora.telegram_interactions(chat_id, status)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_telegram_interactions_received_at ON ancora.telegram_interactions(received_at)"
    )

    op.execute("""
        CREATE TABLE IF NOT EXISTS ancora.telegram_deliveries (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            interaction_id UUID NOT NULL REFERENCES ancora.telegram_interactions(id) ON DELETE CASCADE,
            railway_request_id VARCHAR(255),
            duplicate BOOLEAN NOT NULL DEFAULT FALSE,
            http_status INT,
            delivery_status VARCHAR(31) NOT NULL,
            received_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_telegram_deliveries_interaction ON ancora.telegram_deliveries(interaction_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_telegram_deliveries_received_at ON ancora.telegram_deliveries(received_at)"
    )

    op.execute("""
        CREATE TABLE IF NOT EXISTS ancora.logical_responses (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            interaction_id UUID NOT NULL REFERENCES ancora.telegram_interactions(id) ON DELETE CASCADE,
            response_kind VARCHAR(63) NOT NULL,
            content_ciphertext BYTEA,
            content_key_version INT,
            content_length INT NOT NULL DEFAULT 0,
            chunk_count INT NOT NULL DEFAULT 1,
            status VARCHAR(31) NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_logical_responses_interaction_kind UNIQUE (interaction_id, response_kind)
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_logical_responses_interaction ON ancora.logical_responses(interaction_id)"
    )

    op.execute("""
        CREATE TABLE IF NOT EXISTS ancora.telegram_response_deliveries (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            logical_response_id UUID NOT NULL REFERENCES ancora.logical_responses(id) ON DELETE CASCADE,
            chunk_index INT NOT NULL,
            status VARCHAR(31) NOT NULL,
            telegram_message_id BIGINT,
            started_at TIMESTAMPTZ,
            completed_at TIMESTAMPTZ,
            error_class VARCHAR(127),
            CONSTRAINT uq_response_deliveries_response_chunk UNIQUE (logical_response_id, chunk_index)
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_response_deliveries_response ON ancora.telegram_response_deliveries(logical_response_id)"
    )

    op.execute("""
        CREATE TABLE IF NOT EXISTS ancora.llm_usage_events (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            interaction_id UUID NOT NULL REFERENCES ancora.telegram_interactions(id) ON DELETE CASCADE,
            llm_call_id UUID NOT NULL UNIQUE,
            config_revision BIGINT NOT NULL REFERENCES ancora.runtime_config_revisions(revision) ON DELETE RESTRICT,
            logical_route VARCHAR(127) NOT NULL,
            effective_gateway_route VARCHAR(127) NOT NULL,
            gateway_request_id VARCHAR(255),
            provider_request_id VARCHAR(255),
            provider VARCHAR(63),
            model VARCHAR(255),
            input_tokens INT,
            output_tokens INT,
            total_tokens INT,
            estimated_cost NUMERIC(18, 8),
            actual_cost NUMERIC(18, 8),
            cost_source VARCHAR(31),
            latency_ms INT,
            time_to_first_token_ms INT,
            retry_count INT NOT NULL DEFAULT 0,
            fallback_used BOOLEAN NOT NULL DEFAULT FALSE,
            status VARCHAR(31) NOT NULL,
            error_class VARCHAR(127),
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_llm_usage_interaction ON ancora.llm_usage_events(interaction_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_llm_usage_created_at ON ancora.llm_usage_events(created_at)"
    )

    op.execute(
        "ALTER TABLE ancora.action_proposals ADD COLUMN IF NOT EXISTS source_interaction_id UUID"
    )
    op.execute(
        "ALTER TABLE ancora.action_proposals ADD COLUMN IF NOT EXISTS idempotency_key VARCHAR(255)"
    )
    op.execute(
        "ALTER TABLE ancora.action_proposals ADD COLUMN IF NOT EXISTS arguments_fingerprint VARCHAR(128)"
    )
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM pg_constraint c
                JOIN pg_namespace n ON n.oid = c.connamespace
                WHERE n.nspname = 'ancora'
                  AND c.conname = 'fk_action_proposals_source_interaction'
            ) THEN
                ALTER TABLE ancora.action_proposals
                ADD CONSTRAINT fk_action_proposals_source_interaction
                FOREIGN KEY (source_interaction_id)
                REFERENCES ancora.telegram_interactions(id)
                ON DELETE SET NULL;
            END IF;
        END $$
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_action_proposals_source_interaction ON ancora.action_proposals(source_interaction_id)"
    )
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_action_proposals_idempotency_key
        ON ancora.action_proposals(idempotency_key)
        WHERE idempotency_key IS NOT NULL
    """)


def downgrade() -> None:
    """Remove only the governed LLM access schema and proposal extensions."""
    op.execute("DROP INDEX IF EXISTS ancora.uq_action_proposals_idempotency_key")
    op.execute("DROP INDEX IF EXISTS ancora.idx_action_proposals_source_interaction")
    op.execute(
        "ALTER TABLE ancora.action_proposals DROP CONSTRAINT IF EXISTS fk_action_proposals_source_interaction"
    )
    op.execute("ALTER TABLE ancora.action_proposals DROP COLUMN IF EXISTS arguments_fingerprint")
    op.execute("ALTER TABLE ancora.action_proposals DROP COLUMN IF EXISTS idempotency_key")
    op.execute("ALTER TABLE ancora.action_proposals DROP COLUMN IF EXISTS source_interaction_id")

    op.execute("DROP TABLE IF EXISTS ancora.llm_usage_events CASCADE")
    op.execute("DROP TABLE IF EXISTS ancora.telegram_response_deliveries CASCADE")
    op.execute("DROP TABLE IF EXISTS ancora.logical_responses CASCADE")
    op.execute("DROP TABLE IF EXISTS ancora.telegram_deliveries CASCADE")
    op.execute("DROP TABLE IF EXISTS ancora.telegram_interactions CASCADE")
    op.execute("DROP TABLE IF EXISTS ancora.runtime_config_active CASCADE")
    op.execute("DROP TABLE IF EXISTS ancora.runtime_config_activations CASCADE")
    op.execute("DROP TABLE IF EXISTS ancora.runtime_config_revisions CASCADE")
