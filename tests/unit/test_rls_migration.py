"""Static guards for the phase-1 RLS hardening migration."""

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "migrations/versions/0015_ancora_rls_hardening.py"
INIT_SQL = ROOT / "migrations/init.sql"


def _module():
    spec = importlib.util.spec_from_file_location("rls_hardening", MIGRATION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_rls_migration_follows_current_head_and_covers_future_tables() -> None:
    module = _module()
    source = MIGRATION.read_text(encoding="utf-8")

    assert module.down_revision == "0014_write_trivial_consent_mode"
    assert "n.nspname = 'ancora'" in source
    assert "ENABLE ROW LEVEL SECURITY" in module._rls_sql("ENABLE")
    assert "DISABLE ROW LEVEL SECURITY" in module._rls_sql("DISABLE")
    assert "FORCE ROW LEVEL SECURITY" not in source
    assert "CREATE POLICY" not in source


def test_rls_migration_closes_api_roles_but_preserves_storage_service_role() -> None:
    source = MIGRATION.read_text(encoding="utf-8")

    assert "FROM PUBLIC" in source
    assert "rolname IN ('anon', 'authenticated')" in source
    assert "ALTER DEFAULT PRIVILEGES IN SCHEMA ancora" in source
    assert "service_role" in source  # documented compatibility decision
    assert "service_role'" not in source


def test_init_sql_mirrors_rls_head() -> None:
    init_sql = INIT_SQL.read_text(encoding="utf-8")

    assert "ENABLE ROW LEVEL SECURITY" in init_sql
    assert "REVOKE ALL ON SCHEMA ancora FROM PUBLIC" in init_sql
    assert "rolname IN ('anon', 'authenticated')" in init_sql
    assert "ALTER DEFAULT PRIVILEGES IN SCHEMA ancora" in init_sql
    assert "CREATE POLICY" not in init_sql
