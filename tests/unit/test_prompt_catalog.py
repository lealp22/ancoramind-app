"""Read-only prompt inventory: real content/history, auth and traversal boundaries."""

import json
import shutil
import subprocess
from pathlib import Path
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI

from scripts.export_prompt_history import build_history
from src.agent.admin_dashboard import install_admin_dashboard
from src.agent.health import HealthRegistry
from src.agent.instructions import PROMPTS_DIR, assemble_instructions, load_prompt
from src.agent.prompt_catalog import HISTORY_PATH, ROOT, PromptCatalog, prompt_checksum
from src.config import Settings
from src.domain.runtime_config.models import bootstrap_runtime_configuration
from src.domain.runtime_config.service import RuntimeConfigManager


@pytest.fixture
def catalog(tmp_path: Path) -> PromptCatalog:
    prompts = tmp_path / "prompts"
    source = tmp_path / "src"
    prompts.mkdir()
    source.mkdir()
    (prompts / "skills").mkdir()
    (prompts / "identity.md").write_text("# Identity\nCurrent", encoding="utf-8")
    (prompts / "skills" / "unused.md").write_text("# Unused", encoding="utf-8")
    (source / "instructions.py").write_text(
        'load_prompt("identity.md")\n# load_prompt("skills/unused.md")\n', encoding="utf-8"
    )
    content = "# Identity\nHistorical"
    (tmp_path / "history.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "source_revision": "b" * 40,
                "shallow": False,
                "prompts": {
                    "identity.md": [
                        {
                            "revision": "a" * 40,
                            "committed_at": "2026-10-01T00:00:00Z",
                            "sha256": prompt_checksum(content),
                            "content": content,
                        }
                    ]
                },
            }
        ),
        encoding="utf-8",
    )
    return PromptCatalog(prompts, source, tmp_path / "history.json")


def test_lists_assets_and_literal_call_sites_without_claiming_activation(catalog: PromptCatalog):
    data = catalog.inventory()
    assert data["history_status"] == "available"
    assert data["usage_scan_complete"] is True
    first, unused = data["prompts"]
    assert first["path"] == "identity.md"
    assert first["usages"] == [{"source": "src/instructions.py", "line": 1}]
    assert first["matches_latest_export"] is False
    assert unused["usages"] == []
    assert unused["version_count"] == 0
    assert unused["matches_latest_export"] is None
    assert "content" not in json.dumps(data)
    assert str(catalog.prompts_dir) not in json.dumps(data)


def test_current_and_real_historical_content_are_distinct(catalog: PromptCatalog):
    current = catalog.detail("identity.md")
    historical = catalog.detail("identity.md", "a" * 40)
    assert current["content"] == "# Identity\nCurrent"
    assert historical["content"] == "# Identity\nHistorical"
    assert current["revision"] is None
    assert "content" not in current["versions"][0]
    assert current["sha256"] == prompt_checksum(current["content"])


@pytest.mark.parametrize(
    "name",
    [
        "../.env",
        "../../.env",
        "/etc/passwd",
        "C:\\secret.md",
        "skills/../../secret.md",
        "skills\\unused.md",
        "identity.md/../identity.md",
        "unknown.md",
        ".env",
        "identity.md\x00",
    ],
)
def test_names_are_inventory_keys_not_user_paths(catalog: PromptCatalog, name: str):
    with pytest.raises(KeyError):
        catalog.detail(name)


def test_arbitrary_or_other_prompt_revision_is_rejected(catalog: PromptCatalog):
    for name, revision in [("identity.md", "HEAD"), ("skills/unused.md", "a" * 40)]:
        with pytest.raises(KeyError):
            catalog.detail(name, revision)


@pytest.mark.parametrize("content", [None, "{bad json", '{"schema_version":2}'])
def test_missing_or_invalid_history_does_not_fabricate_versions(catalog: PromptCatalog, content):
    if content is None:
        catalog.history_path.unlink()
    else:
        catalog.history_path.write_text(content, encoding="utf-8")
    data = catalog.inventory()
    assert data["history_status"] == ("unavailable" if content is None else "invalid")
    assert data["prompts"][0]["version_count"] == 0
    assert catalog.detail("identity.md")["content"] == "# Identity\nCurrent"


def test_corrupt_historical_hash_is_not_presented(catalog: PromptCatalog):
    data = json.loads(catalog.history_path.read_text(encoding="utf-8"))
    data["prompts"]["identity.md"][0]["content"] = "tampered"
    catalog.history_path.write_text(json.dumps(data), encoding="utf-8")
    assert catalog.inventory()["history_status"] == "invalid"
    with pytest.raises(KeyError):
        catalog.detail("identity.md", "a" * 40)


def test_partial_usage_scan_is_explicit(catalog: PromptCatalog):
    (catalog.source_dir / "broken.py").write_text("syntax error(", encoding="utf-8")
    assert catalog.inventory()["usage_scan_complete"] is False


def test_symlink_assets_and_directories_are_not_exposed(catalog: PromptCatalog, tmp_path: Path):
    outside = tmp_path / "private.md"
    outside.write_text("private", encoding="utf-8")
    try:
        (catalog.prompts_dir / "link.md").symlink_to(outside)
    except OSError:
        pytest.skip("Symlink permission unavailable")
    assert "link.md" not in {p["path"] for p in catalog.inventory()["prompts"]}
    with pytest.raises(KeyError):
        catalog.detail("link.md")


def _app(catalog: PromptCatalog, enabled: bool = True):
    session = AsyncMock()
    settings = Settings(
        _env_file=None,
        admin_dashboard_enabled=enabled,
        admin_dashboard_token="dashboard-test",
        ancora_database_url="postgresql+asyncpg://test:test@localhost/test",
        telegram_pairing_code_pepper="test-pepper",
    )
    app = FastAPI()
    install_admin_dashboard(
        app,
        settings,
        session,
        health_registry=HealthRegistry(),
        runtime_config_manager=RuntimeConfigManager(
            session_factory=AsyncMock(), bootstrap=bootstrap_runtime_configuration()
        ),
        prompt_catalog=catalog,
    )
    return app, session


@pytest.mark.parametrize("path", ["/prompts", "/prompts/detail?path=identity.md"])
@pytest.mark.parametrize("token", [None, "wrong", "runtime-config-token"])
async def test_routes_authenticate_before_reading(catalog: PromptCatalog, path, token, monkeypatch):
    app, session = _app(catalog)

    def forbidden(*args):
        pytest.fail("Catalog accessed before authentication")

    monkeypatch.setattr(catalog, "inventory", forbidden)
    monkeypatch.setattr(catalog, "detail", forbidden)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app), base_url="http://test"
    ) as client:
        response = await client.get(
            "/admin/dashboard/api" + path,
            headers={"Authorization": f"Bearer {token}"} if token else {},
        )
    assert response.status_code == 401
    session.assert_not_called()


async def test_routes_only_read_and_never_access_database(catalog: PromptCatalog):
    app, session = _app(catalog)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app),
        base_url="http://test",
        headers={"Authorization": "Bearer dashboard-test"},
    ) as client:
        listed = await client.get("/admin/dashboard/api/prompts")
        response = await client.get(
            "/admin/dashboard/api/prompts/detail",
            params={
                "path": "identity.md",
                "revision": "a" * 40,
            },
        )
        missing = await client.get(
            "/admin/dashboard/api/prompts/detail", params={"path": "../.env"}
        )
        mutation = await client.post("/admin/dashboard/api/prompts")
    assert listed.status_code == response.status_code == 200
    assert response.json()["content"] == "# Identity\nHistorical"
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert missing.status_code == 404
    assert mutation.status_code == 405
    session.assert_not_called()


async def test_prompt_routes_absent_when_dashboard_disabled(catalog: PromptCatalog):
    app, _ = _app(catalog, False)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app), base_url="http://test"
    ) as client:
        for path in ("/prompts", "/prompts/detail?path=identity.md"):
            assert (await client.get("/admin/dashboard/api" + path)).status_code == 404


def test_real_catalog_covers_assets_and_actual_loader_references():
    catalog = PromptCatalog()
    entries = {p["path"]: p for p in catalog.inventory()["prompts"]}
    assert set(entries) == {
        p.relative_to(PROMPTS_DIR).as_posix() for p in PROMPTS_DIR.rglob("*.md")
    }
    assert all(v["usages"] for k, v in entries.items() if load_prompt(k) in assemble_instructions())
    assert entries["skills/presentation.md"]["usages"]
    assert entries["skills/document_extraction.md"]["usages"]
    assert not entries["skills/reminders.md"]["usages"]
    assert not entries["skills/dream.md"]["usages"]


def test_packaged_history_works_without_git_and_survives_line_endings(tmp_path: Path):
    packaged = tmp_path / "package"
    shutil.copytree(PROMPTS_DIR, packaged / "prompts")
    shutil.copytree(ROOT / "src", packaged / "src", ignore=shutil.ignore_patterns("__pycache__"))
    catalog = PromptCatalog(packaged / "prompts", packaged / "src", HISTORY_PATH)
    assert not (packaged / ".git").exists()
    assert catalog.inventory()["history_status"] == "available"
    assert all(p["matches_latest_export"] for p in catalog.inventory()["prompts"])
    assert prompt_checksum("\r\n a\r\nb \r\n") == prompt_checksum("a\nb")


@pytest.mark.skipif(shutil.which("git") is None, reason="Git needed to test offline exporter")
def test_exporter_records_real_versions_only_and_excludes_identity_metadata(tmp_path: Path):
    def git(*args):
        return subprocess.check_output(["git", "-C", str(tmp_path), *args], text=True).strip()

    git("init", "-q")
    git("config", "user.email", "synthetic@example.invalid")
    git("config", "user.name", "Synthetic")
    (tmp_path / "prompts").mkdir()
    prompt = tmp_path / "prompts" / "identity.md"
    prompt.write_text("First", encoding="utf-8")
    git("add", "prompts")
    git("commit", "-qm", "private commit message")
    first = git("rev-parse", "HEAD")
    prompt.write_text("Second", encoding="utf-8")
    git("add", "prompts")
    git("commit", "-qm", "second")
    data = build_history(tmp_path)
    versions = data["prompts"]["identity.md"]
    assert [v["content"] for v in versions] == ["Second", "First"]
    assert versions[1]["revision"] == first
    assert "synthetic@example.invalid" not in json.dumps(data)
    assert "private commit message" not in json.dumps(data)


def test_prompt_ui_is_text_only_and_clears_content_on_logout():
    source = (ROOT / "src/agent/admin_dashboard_static/dashboard.html").read_text(encoding="utf-8")
    block = source.split("// ---- Prompt inventory:", 1)[1].split("// ---- FinOps y calidad", 1)[0]
    for forbidden in ("innerHTML", "outerHTML", "insertAdjacentHTML", "eval("):
        assert forbidden not in block
    assert 'document.getElementById("prompt-content").textContent = data.content' in block
    assert "clearPrompts();" in source.split("function logout(reason)", 1)[1].split("}", 1)[0]
    assert "new URLSearchParams({path: name})" in block
    assert "request !== promptRequest" in block
