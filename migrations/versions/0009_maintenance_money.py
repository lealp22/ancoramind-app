"""Align vehicle maintenance schema with canonical money and proposal idempotency.

Revision ID: 0009_maintenance_money
Revises: 0008_document_semantic_retrieval
Create Date: 2026-10-04
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0009_maintenance_money"
down_revision: str | None = "0008_document_semantic_retrieval"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Repair historical columns and introduce canonical monetary fields."""
    # A NUMERIC ``cost`` from the drifted schema has no associated currency. Do
    # not silently label it: an operator must resolve any such historical rows.
    op.execute("""
        DO $$
        DECLARE
            has_legacy_cost boolean;
            has_legacy_values boolean;
        BEGIN
            SELECT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_schema = 'ancora' AND table_name = 'vehicle_maintenance'
                  AND column_name = 'cost'
            ) INTO has_legacy_cost;
            IF has_legacy_cost THEN
                EXECUTE 'SELECT EXISTS (SELECT 1 FROM ancora.vehicle_maintenance WHERE cost IS NOT NULL)'
                INTO has_legacy_values;
                IF has_legacy_values THEN
                    RAISE EXCEPTION
                        'vehicle_maintenance.cost has values without currency; resolve them before 0009';
                END IF;
            END IF;
        END $$
    """)
    op.execute("ALTER TABLE ancora.vehicle_maintenance ADD COLUMN IF NOT EXISTS work_performed JSONB NOT NULL DEFAULT '[]'::jsonb")
    op.execute("ALTER TABLE ancora.vehicle_maintenance ADD COLUMN IF NOT EXISTS notes TEXT")
    op.execute("ALTER TABLE ancora.vehicle_maintenance ADD COLUMN IF NOT EXISTS cost_amount NUMERIC(14,2)")
    op.execute("ALTER TABLE ancora.vehicle_maintenance ADD COLUMN IF NOT EXISTS cost_currency CHAR(3)")
    op.execute("ALTER TABLE ancora.vehicle_maintenance ADD COLUMN IF NOT EXISTS source_action_id UUID")
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint c JOIN pg_namespace n ON n.oid = c.connamespace
                WHERE n.nspname = 'ancora' AND c.conname = 'fk_vehicle_maintenance_source_action'
            ) THEN
                ALTER TABLE ancora.vehicle_maintenance
                ADD CONSTRAINT fk_vehicle_maintenance_source_action
                FOREIGN KEY (source_action_id) REFERENCES ancora.action_proposals(id) ON DELETE SET NULL;
            END IF;
        END $$
    """)
    op.execute("ALTER TABLE ancora.vehicle_maintenance DROP COLUMN IF EXISTS cost")
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint c JOIN pg_namespace n ON n.oid = c.connamespace
                WHERE n.nspname = 'ancora' AND c.conname = 'ck_vehicle_maintenance_cost_pair'
            ) THEN
                ALTER TABLE ancora.vehicle_maintenance
                ADD CONSTRAINT ck_vehicle_maintenance_cost_pair
                CHECK ((cost_amount IS NULL) = (cost_currency IS NULL)) NOT VALID;
            END IF;
        END $$
    """)
    op.execute("ALTER TABLE ancora.vehicle_maintenance VALIDATE CONSTRAINT ck_vehicle_maintenance_cost_pair")
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint c JOIN pg_namespace n ON n.oid = c.connamespace
                WHERE n.nspname = 'ancora' AND c.conname = 'ck_vehicle_maintenance_cost_amount_nonnegative'
            ) THEN
                ALTER TABLE ancora.vehicle_maintenance
                ADD CONSTRAINT ck_vehicle_maintenance_cost_amount_nonnegative
                CHECK (cost_amount IS NULL OR cost_amount >= 0) NOT VALID;
            END IF;
        END $$
    """)
    op.execute("ALTER TABLE ancora.vehicle_maintenance VALIDATE CONSTRAINT ck_vehicle_maintenance_cost_amount_nonnegative")
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint c JOIN pg_namespace n ON n.oid = c.connamespace
                WHERE n.nspname = 'ancora' AND c.conname = 'ck_vehicle_maintenance_cost_currency_iso'
            ) THEN
                ALTER TABLE ancora.vehicle_maintenance
                ADD CONSTRAINT ck_vehicle_maintenance_cost_currency_iso
                CHECK (cost_currency IS NULL OR cost_currency ~ '^[A-Z]{3}$') NOT VALID;
            END IF;
        END $$
    """)
    op.execute("ALTER TABLE ancora.vehicle_maintenance VALIDATE CONSTRAINT ck_vehicle_maintenance_cost_currency_iso")
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_vehicle_maintenance_source_action
        ON ancora.vehicle_maintenance(source_action_id)
        WHERE source_action_id IS NOT NULL
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ancora.uq_vehicle_maintenance_source_action")
    for constraint in (
        "ck_vehicle_maintenance_cost_currency_iso",
        "ck_vehicle_maintenance_cost_amount_nonnegative",
        "ck_vehicle_maintenance_cost_pair",
        "fk_vehicle_maintenance_source_action",
    ):
        op.execute(f"ALTER TABLE ancora.vehicle_maintenance DROP CONSTRAINT IF EXISTS {constraint}")
    op.execute("ALTER TABLE ancora.vehicle_maintenance DROP COLUMN IF EXISTS source_action_id")
    op.execute("ALTER TABLE ancora.vehicle_maintenance DROP COLUMN IF EXISTS cost_currency")
    op.execute("ALTER TABLE ancora.vehicle_maintenance DROP COLUMN IF EXISTS cost_amount")
