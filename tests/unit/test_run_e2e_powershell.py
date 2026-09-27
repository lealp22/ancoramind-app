"""Smoke tests for the safe, no-side-effect validation mode of run-e2e.ps1."""

from __future__ import annotations

import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "run-e2e.ps1"


def _normalize_powershell_output(value: str) -> str:
    """Collapse display wrapping that Windows PowerShell inserts into stderr."""
    return " ".join(value.split())


def _run_check(env_file: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(SCRIPT_PATH),
            "-Check",
            "-PublicBaseUrl",
            "https://ancoramind-app-production.up.railway.app",
            "-EnvFile",
            str(env_file),
        ],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def _managed_env(extra: str = "") -> str:
    return "\n".join(
        [
            "TELEGRAM_TOKEN=synthetic-token",
            "LLM_PROVIDER=openrouter",
            "OPENROUTER_API_KEY=synthetic-openrouter-key",
            "ANCORA_DATABASE_URL=postgresql+asyncpg://user:pass@db.example.test:5432/ancoramind",
            "DOCUMENT_STORAGE_BACKEND=local",
            extra,
        ]
    )


def test_check_mode_validates_managed_configuration_without_side_effects(tmp_path: Path) -> None:
    env_file = tmp_path / "valid.env"
    env_file.write_text(_managed_env(), encoding="utf-8")

    result = _run_check(env_file)

    assert result.returncode == 0, result.stderr
    assert "Prerequisites OK" in result.stdout
    assert "Check-only mode" in result.stdout


def test_check_mode_reads_dotenv_as_literal_data_not_powershell(tmp_path: Path) -> None:
    sentinel = tmp_path / "must-not-exist.txt"
    env_file = tmp_path / "literal.env"
    env_file.write_text(
        _managed_env(f"UNTRUSTED=$(New-Item -Path '{sentinel}')"),
        encoding="utf-8",
    )

    result = _run_check(env_file)

    assert result.returncode == 0, result.stderr
    assert not sentinel.exists()


def test_check_mode_rejects_unknown_provider(tmp_path: Path) -> None:
    env_file = tmp_path / "invalid.env"
    invalid_config = _managed_env().replace("LLM_PROVIDER=openrouter", "LLM_PROVIDER=unknown")
    env_file.write_text(invalid_config, encoding="utf-8")

    result = _run_check(env_file)

    assert result.returncode == 1
    assert "Unknown LLM_PROVIDER" in _normalize_powershell_output(result.stderr)


def test_check_mode_rejects_public_base_url_with_a_path(tmp_path: Path) -> None:
    env_file = tmp_path / "valid.env"
    env_file.write_text(_managed_env(), encoding="utf-8")

    result = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(SCRIPT_PATH),
            "-Check",
            "-PublicBaseUrl",
            "https://ancoramind-app-production.up.railway.app/not-allowed",
            "-EnvFile",
            str(env_file),
        ],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1
    assert "PublicBaseUrl must be a clean HTTPS URL" in _normalize_powershell_output(result.stderr)
