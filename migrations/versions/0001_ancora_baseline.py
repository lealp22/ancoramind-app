"""AncoraMind canonical schema before governed LLM access.

Revision ID: 0001_ancora_baseline
Revises: None
Create Date: 2026-09-13
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0001_ancora_baseline"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the legacy baseline idempotently for empty or existing databases."""
    op.execute("CREATE SCHEMA IF NOT EXISTS agno_runtime")
    op.execute("CREATE SCHEMA IF NOT EXISTS ancora")

    op.execute("""
        CREATE TABLE IF NOT EXISTS ancora.notes (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id VARCHAR(255) NOT NULL,
            content TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_notes_user_id ON ancora.notes(user_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_notes_created_at ON ancora.notes(created_at DESC)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS ancora.documents (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id VARCHAR(255) NOT NULL,
            storage_key TEXT NOT NULL,
            original_filename TEXT NOT NULL,
            mime_type VARCHAR(127) NOT NULL,
            size_bytes BIGINT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_docs_user_id ON ancora.documents(user_id)")
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_docs_created_at ON ancora.documents(created_at DESC)"
    )

    op.execute("""
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
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_extractions_doc_id ON ancora.ai_extractions(document_id)"
    )

    op.execute("""
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
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_vehicles_user_id ON ancora.vehicles(user_id)")

    op.execute("""
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
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_maint_vehicle_id ON ancora.vehicle_maintenance(vehicle_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_maint_user_id ON ancora.vehicle_maintenance(user_id)"
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_maint_date ON ancora.vehicle_maintenance(date DESC)")

    op.execute("""
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
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_proposals_user_status ON ancora.action_proposals(user_id, status)"
    )

    op.execute("""
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
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_reminders_user_status ON ancora.reminders(user_id, status)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_reminders_trigger_at ON ancora.reminders(trigger_at)"
    )

    op.execute("""
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
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_calendar_user_start ON ancora.calendar_events(user_id, start_at)"
    )

    op.execute("""
        CREATE TABLE IF NOT EXISTS ancora.todo_lists (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id VARCHAR(255) NOT NULL,
            name VARCHAR(200) NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_todo_lists_user_id ON ancora.todo_lists(user_id)")

    op.execute("""
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
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_todo_items_list_id ON ancora.todo_items(list_id)")
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_todo_items_user_status ON ancora.todo_items(user_id, status)"
    )


def downgrade() -> None:
    """Remove the complete legacy domain baseline."""
    op.execute("DROP TABLE IF EXISTS ancora.todo_items CASCADE")
    op.execute("DROP TABLE IF EXISTS ancora.todo_lists CASCADE")
    op.execute("DROP TABLE IF EXISTS ancora.calendar_events CASCADE")
    op.execute("DROP TABLE IF EXISTS ancora.reminders CASCADE")
    op.execute("DROP TABLE IF EXISTS ancora.action_proposals CASCADE")
    op.execute("DROP TABLE IF EXISTS ancora.vehicle_maintenance CASCADE")
    op.execute("DROP TABLE IF EXISTS ancora.vehicles CASCADE")
    op.execute("DROP TABLE IF EXISTS ancora.ai_extractions CASCADE")
    op.execute("DROP TABLE IF EXISTS ancora.documents CASCADE")
    op.execute("DROP TABLE IF EXISTS ancora.notes CASCADE")
