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

-- Domain tables will be added via Alembic migrations in subsequent milestones

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