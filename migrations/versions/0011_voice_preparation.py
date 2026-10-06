"""Durable exclusive voice preparation, no audio storage (specs/028 T3)."""

from collections.abc import Sequence

from alembic import op

revision: str = "0011_voice_preparation"
down_revision: str | None = "0010_pairing_auto_approve"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DDL = """
CREATE TABLE IF NOT EXISTS ancora.voice_preparations (
    interaction_id UUID PRIMARY KEY REFERENCES ancora.telegram_interactions(id) ON DELETE CASCADE,
    user_id BIGINT NOT NULL,
    owner_token UUID NOT NULL,
    status VARCHAR(31) NOT NULL CHECK (status IN (
        'preparing', 'downloaded', 'transcribing', 'transcribed',
        'failed_controlled', 'failed_ambiguous')),
    config_revision BIGINT NOT NULL CHECK (config_revision >= 0),
    call_id UUID UNIQUE,
    logical_route VARCHAR(127),
    effective_route VARCHAR(127),
    duration_seconds NUMERIC(18,9) CHECK (duration_seconds > 0 AND duration_seconds <= 300),
    size_bytes INT CHECK (size_bytes > 0 AND size_bytes <= 10485760),
    estimated_cost NUMERIC CHECK (estimated_cost >= 0 AND estimated_cost <> 'NaN'::numeric),
    actual_cost NUMERIC CHECK (actual_cost >= 0 AND actual_cost <> 'NaN'::numeric),
    transcript_ciphertext BYTEA,
    transcript_key_version INT CHECK (transcript_key_version > 0),
    transcript_expires_at TIMESTAMPTZ,
    claimed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK ((transcript_ciphertext IS NULL AND transcript_key_version IS NULL
            AND transcript_expires_at IS NULL)
        OR (transcript_ciphertext IS NOT NULL AND transcript_key_version IS NOT NULL
            AND transcript_expires_at IS NOT NULL)),
    CHECK (status NOT IN ('transcribing', 'transcribed') OR
        (call_id IS NOT NULL AND logical_route IS NOT NULL AND effective_route IS NOT NULL
         AND duration_seconds IS NOT NULL AND size_bytes IS NOT NULL AND estimated_cost IS NOT NULL))
);
CREATE INDEX IF NOT EXISTS idx_voice_preparations_expiry
    ON ancora.voice_preparations(transcript_expires_at)
    WHERE transcript_ciphertext IS NOT NULL;

CREATE OR REPLACE FUNCTION ancora.voice_preparation_parent_guard()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE voice_status text; voice_cipher bytea; voice_expiry timestamptz;
BEGIN
    SELECT status, transcript_ciphertext, transcript_expires_at
    INTO voice_status, voice_cipher, voice_expiry FROM ancora.voice_preparations
    WHERE interaction_id = NEW.id;
    IF NEW.status = 'agent_started' AND voice_status IS NOT NULL
       AND (voice_status <> 'transcribed' OR voice_cipher IS NULL OR voice_expiry <= now()) THEN
        RAISE EXCEPTION 'voice preparation incomplete';
    END IF;
    IF NEW.status IN ('completed', 'ignored', 'rejected', 'failed_controlled', 'failed_definitive')
       OR (NEW.status = 'failed_ambiguous' AND NEW.payload_ciphertext IS NULL) THEN
        UPDATE ancora.voice_preparations
        SET transcript_ciphertext = NULL, transcript_key_version = NULL,
            transcript_expires_at = NULL
        WHERE interaction_id = NEW.id AND transcript_ciphertext IS NOT NULL;
    ELSIF NEW.status = 'failed_ambiguous' AND NEW.completed_at IS NOT NULL THEN
        UPDATE ancora.voice_preparations
        SET transcript_expires_at = LEAST(transcript_expires_at,
                                         NEW.completed_at + interval '7 days')
        WHERE interaction_id = NEW.id AND transcript_ciphertext IS NOT NULL
          AND transcript_expires_at > NEW.completed_at + interval '7 days';
    END IF;
    RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS trg_voice_preparation_parent_guard ON ancora.telegram_interactions;
CREATE TRIGGER trg_voice_preparation_parent_guard
    BEFORE UPDATE ON ancora.telegram_interactions
    FOR EACH ROW EXECUTE FUNCTION ancora.voice_preparation_parent_guard();
"""


def upgrade() -> None:
    op.execute(DDL)


def downgrade() -> None:
    # Do not return abandoned voice work to the legacy accepted queue.
    op.execute("""
        UPDATE ancora.telegram_interactions i
        SET status = 'failed_ambiguous', completed_at = now(), updated_at = now(),
            error_class = 'VoicePreparationDowngrade', error_detail_code = 'voice_schema_removed'
        WHERE i.status = 'accepted' AND EXISTS (
            SELECT 1 FROM ancora.voice_preparations v WHERE v.interaction_id = i.id);
        DROP TRIGGER IF EXISTS trg_voice_preparation_parent_guard ON ancora.telegram_interactions;
        DROP FUNCTION IF EXISTS ancora.voice_preparation_parent_guard();
        DROP TABLE IF EXISTS ancora.voice_preparations;
    """)
