-- AncoraMind — Initial PostgreSQL schema setup
-- Creates separate schemas for Agno runtime and AncoraMind domain

-- Agno runtime schema (managed by Agno, created here for initialization)
CREATE SCHEMA IF NOT EXISTS agno_runtime;

-- AncoraMind domain schema (managed by AncoraMind Core)
CREATE SCHEMA IF NOT EXISTS ancora;

-- Grant basic permissions
GRANT USAGE ON SCHEMA agno_runtime TO ancora;
GRANT USAGE ON SCHEMA ancora TO ancora;
GRANT CREATE ON SCHEMA agno_runtime TO ancora;
GRANT CREATE ON SCHEMA ancora TO ancora;

-- Alembic is the canonical migration history. This file mirrors Alembic head
-- for fresh/local bootstrap and remains idempotent.

-- ── AncoraMind Domain Tables ──────────────────────

-- Personal notes — canonical memory (M2)
CREATE TABLE IF NOT EXISTS ancora.notes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id VARCHAR(255) NOT NULL,
    content TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_notes_user_id ON ancora.notes(user_id);
CREATE INDEX IF NOT EXISTS idx_notes_created_at ON ancora.notes(created_at DESC);
-- Document memory (M3)
CREATE TABLE IF NOT EXISTS ancora.documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id VARCHAR(255) NOT NULL,
    storage_key TEXT NOT NULL,
    original_filename TEXT NOT NULL,
    mime_type VARCHAR(127) NOT NULL,
    size_bytes BIGINT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_docs_user_id ON ancora.documents(user_id);
CREATE INDEX IF NOT EXISTS idx_docs_created_at ON ancora.documents(created_at DESC);

CREATE TABLE IF NOT EXISTS ancora.ai_extractions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID NOT NULL REFERENCES ancora.documents(id) ON DELETE CASCADE,
    provider VARCHAR(63) NOT NULL,
    model VARCHAR(127) NOT NULL,
    prompt_version VARCHAR(31) NOT NULL,
    schema_version VARCHAR(31) NOT NULL,
    extraction JSONB NOT NULL DEFAULT '{}',
    confidence FLOAT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_extractions_doc_id ON ancora.ai_extractions(document_id);
-- Vehicles (M4)
CREATE TABLE IF NOT EXISTS ancora.vehicles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id VARCHAR(255) NOT NULL,
    make VARCHAR(100) NOT NULL,
    model VARCHAR(100) NOT NULL,
    year INT,
    registration VARCHAR(20),
    nickname VARCHAR(100),
    vin VARCHAR(50),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_vehicles_user_id ON ancora.vehicles(user_id);

CREATE TABLE IF NOT EXISTS ancora.vehicle_maintenance (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    vehicle_id UUID NOT NULL REFERENCES ancora.vehicles(id) ON DELETE CASCADE,
    user_id VARCHAR(255) NOT NULL,
    date DATE NOT NULL,
    mileage_km INT,
    description VARCHAR(2000) NOT NULL,
    workshop VARCHAR(200),
    cost VARCHAR(50),
    work_performed JSONB NOT NULL DEFAULT '[]',
    notes TEXT,
    source_document_id UUID REFERENCES ancora.documents(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_maint_vehicle_id ON ancora.vehicle_maintenance(vehicle_id);
CREATE INDEX IF NOT EXISTS idx_maint_user_id ON ancora.vehicle_maintenance(user_id);
CREATE INDEX IF NOT EXISTS idx_maint_date ON ancora.vehicle_maintenance(date DESC);

-- Action proposals (M4 — governance)
CREATE TABLE IF NOT EXISTS ancora.action_proposals (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id VARCHAR(255) NOT NULL,
    tool_name VARCHAR(127) NOT NULL,
    status VARCHAR(31) NOT NULL DEFAULT 'pending_confirmation',
    payload JSONB NOT NULL DEFAULT '{}',
    source_document_id UUID REFERENCES ancora.documents(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    confirmed_at TIMESTAMPTZ,
    executed_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_proposals_user_status ON ancora.action_proposals(user_id, status);
-- Reminders (M5)
CREATE TABLE IF NOT EXISTS ancora.reminders (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id VARCHAR(255) NOT NULL,
    title VARCHAR(500) NOT NULL,
    description TEXT,
    trigger_at TIMESTAMPTZ NOT NULL,
    status VARCHAR(31) NOT NULL DEFAULT 'pending',
    source_document_id UUID REFERENCES ancora.documents(id) ON DELETE SET NULL,
    source_action_id UUID REFERENCES ancora.action_proposals(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_reminders_user_status ON ancora.reminders(user_id, status);
CREATE INDEX IF NOT EXISTS idx_reminders_trigger_at ON ancora.reminders(trigger_at);

-- Calendar events (M5)
CREATE TABLE IF NOT EXISTS ancora.calendar_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id VARCHAR(255) NOT NULL,
    title VARCHAR(500) NOT NULL,
    description TEXT,
    location VARCHAR(500),
    start_at TIMESTAMPTZ NOT NULL,
    end_at TIMESTAMPTZ,
    provider_event_id VARCHAR(255),
    source_document_id UUID REFERENCES ancora.documents(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_calendar_user_start ON ancora.calendar_events(user_id, start_at);

-- Todo lists (BL-21)
CREATE TABLE IF NOT EXISTS ancora.todo_lists (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id VARCHAR(255) NOT NULL,
    name VARCHAR(200) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_todo_lists_user_id ON ancora.todo_lists(user_id);

CREATE TABLE IF NOT EXISTS ancora.todo_items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    list_id UUID NOT NULL REFERENCES ancora.todo_lists(id) ON DELETE CASCADE,
    user_id VARCHAR(255) NOT NULL,
    title VARCHAR(500) NOT NULL,
    description TEXT,
    status VARCHAR(31) NOT NULL DEFAULT 'pending',
    priority VARCHAR(31),
    due_date TIMESTAMPTZ,
    position INT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_todo_items_list_id ON ancora.todo_items(list_id);
CREATE INDEX IF NOT EXISTS idx_todo_items_user_status ON ancora.todo_items(user_id, status);

-- ── Governed LLM access + Telegram admission (BL-23 / specs/013) ──

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
);
CREATE INDEX IF NOT EXISTS idx_runtime_config_created_at
    ON ancora.runtime_config_revisions(created_at DESC);

CREATE TABLE IF NOT EXISTS ancora.runtime_config_active (
    singleton_id BOOLEAN PRIMARY KEY DEFAULT TRUE CHECK (singleton_id),
    active_revision BIGINT NOT NULL
        REFERENCES ancora.runtime_config_revisions(revision) ON DELETE RESTRICT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS ancora.runtime_config_activations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    revision BIGINT NOT NULL
        REFERENCES ancora.runtime_config_revisions(revision) ON DELETE RESTRICT,
    previous_revision BIGINT
        REFERENCES ancora.runtime_config_revisions(revision) ON DELETE RESTRICT,
    actor VARCHAR(255) NOT NULL,
    reason TEXT NOT NULL,
    activated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_runtime_config_activations_revision
    ON ancora.runtime_config_activations(revision);

-- Governed Telegram evaluator onboarding (BL-24)
-- Redeemable invitation codes are stored only as keyed hashes.
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
);
CREATE INDEX IF NOT EXISTS idx_pairing_invitations_active_expiry
    ON ancora.telegram_pairing_invitations(expires_at)
    WHERE status = 'active';

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
);
CREATE INDEX IF NOT EXISTS idx_pairing_requests_pending
    ON ancora.telegram_pairing_requests(requested_at)
    WHERE status = 'pending';

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
);
CREATE INDEX IF NOT EXISTS idx_pairing_authorizations_active
    ON ancora.telegram_pairing_authorizations(telegram_user_id)
    WHERE status = 'active';

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
    config_revision BIGINT
        REFERENCES ancora.runtime_config_revisions(revision) ON DELETE RESTRICT,
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
    CONSTRAINT uq_telegram_interactions_bot_update
        UNIQUE (bot_id, telegram_update_id),
    CONSTRAINT uq_telegram_interactions_agno_run UNIQUE (agno_run_id)
);
CREATE INDEX IF NOT EXISTS idx_telegram_interactions_status
    ON ancora.telegram_interactions(status);
CREATE INDEX IF NOT EXISTS idx_telegram_interactions_chat_status
    ON ancora.telegram_interactions(chat_id, status);
CREATE INDEX IF NOT EXISTS idx_telegram_interactions_received_at
    ON ancora.telegram_interactions(received_at);
CREATE INDEX IF NOT EXISTS idx_telegram_interactions_user_accepted_at
    ON ancora.telegram_interactions(telegram_user_id, accepted_at)
    WHERE accepted_at IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_telegram_interactions_accepted_queue
    ON ancora.telegram_interactions(received_at)
    WHERE status = 'accepted';

CREATE TABLE IF NOT EXISTS ancora.telegram_deliveries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    interaction_id UUID NOT NULL
        REFERENCES ancora.telegram_interactions(id) ON DELETE CASCADE,
    railway_request_id VARCHAR(255),
    duplicate BOOLEAN NOT NULL DEFAULT FALSE,
    http_status INT,
    delivery_status VARCHAR(31) NOT NULL,
    received_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_telegram_deliveries_interaction
    ON ancora.telegram_deliveries(interaction_id);
CREATE INDEX IF NOT EXISTS idx_telegram_deliveries_received_at
    ON ancora.telegram_deliveries(received_at);

CREATE TABLE IF NOT EXISTS ancora.logical_responses (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    interaction_id UUID NOT NULL
        REFERENCES ancora.telegram_interactions(id) ON DELETE CASCADE,
    response_kind VARCHAR(63) NOT NULL,
    content_ciphertext BYTEA,
    content_key_version INT,
    content_length INT NOT NULL DEFAULT 0,
    chunk_count INT NOT NULL DEFAULT 1,
    status VARCHAR(31) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_logical_responses_interaction_kind
        UNIQUE (interaction_id, response_kind)
);
CREATE INDEX IF NOT EXISTS idx_logical_responses_interaction
    ON ancora.logical_responses(interaction_id);

CREATE TABLE IF NOT EXISTS ancora.telegram_response_deliveries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    logical_response_id UUID NOT NULL
        REFERENCES ancora.logical_responses(id) ON DELETE CASCADE,
    chunk_index INT NOT NULL,
    status VARCHAR(31) NOT NULL,
    telegram_message_id BIGINT,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    error_class VARCHAR(127),
    CONSTRAINT uq_response_deliveries_response_chunk
        UNIQUE (logical_response_id, chunk_index)
);
CREATE INDEX IF NOT EXISTS idx_response_deliveries_response
    ON ancora.telegram_response_deliveries(logical_response_id);

CREATE TABLE IF NOT EXISTS ancora.llm_usage_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    interaction_id UUID NOT NULL
        REFERENCES ancora.telegram_interactions(id) ON DELETE CASCADE,
    llm_call_id UUID NOT NULL UNIQUE,
    config_revision BIGINT NOT NULL
        REFERENCES ancora.runtime_config_revisions(revision) ON DELETE RESTRICT,
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
);
CREATE INDEX IF NOT EXISTS idx_llm_usage_interaction
    ON ancora.llm_usage_events(interaction_id);
CREATE INDEX IF NOT EXISTS idx_llm_usage_created_at
    ON ancora.llm_usage_events(created_at);

ALTER TABLE ancora.action_proposals
    ADD COLUMN IF NOT EXISTS source_interaction_id UUID;
ALTER TABLE ancora.action_proposals
    ADD COLUMN IF NOT EXISTS idempotency_key VARCHAR(255);
ALTER TABLE ancora.action_proposals
    ADD COLUMN IF NOT EXISTS arguments_fingerprint VARCHAR(128);

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
END $$;

CREATE INDEX IF NOT EXISTS idx_action_proposals_source_interaction
    ON ancora.action_proposals(source_interaction_id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_action_proposals_idempotency_key
    ON ancora.action_proposals(idempotency_key)
    WHERE idempotency_key IS NOT NULL;
