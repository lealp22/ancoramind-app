"""Static guards for the Supabase function search-path hardening migration."""

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "migrations/versions/0016_voice_guard_search_path.py"
INIT_SQL = ROOT / "migrations/init.sql"


def _module():
    spec = importlib.util.spec_from_file_location("voice_guard_search_path", MIGRATION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_migration_follows_rls_head_and_pins_an_empty_search_path() -> None:
    module = _module()
    source = MIGRATION.read_text(encoding="utf-8")

    assert module.down_revision == "0015_ancora_rls_hardening"
    assert "ALTER FUNCTION ancora.voice_preparation_parent_guard()" in source
    assert "SET search_path = ''" in source
    assert "RESET search_path" in source


def test_init_sql_defines_the_function_with_an_empty_search_path() -> None:
    init_sql = INIT_SQL.read_text(encoding="utf-8")
    function_start = init_sql.index(
        "CREATE OR REPLACE FUNCTION ancora.voice_preparation_parent_guard()"
    )
    function_end = init_sql.index("END $$;", function_start)
    function_ddl = init_sql[function_start:function_end]

    assert "SET search_path = ''" in function_ddl
    assert "ancora.voice_preparations" in function_ddl
