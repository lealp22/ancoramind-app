"""Root-context workaround preserves sources and never uploads or spends."""

import io
import subprocess
import tarfile
from pathlib import Path

import pytest

from scripts import prepare_eval_build as build
from scripts.eval_source import source_fingerprint


@pytest.fixture
def source(tmp_path):
    contents = {
        "pyproject.toml": b"# synthetic\n", "README.md": b"synthetic",
        "evals/Dockerfile": b"FROM python:3.12-slim\n",
        "evals/Dockerfile.dockerignore": b"**\n!src/**\n",
        "evals/cases.json": b"{}", "scripts/eval_service.py": b"# idle\n",
        "src/example.py": b"# synthetic\n", "prompts/example.md": b"synthetic",
        "Dockerfile": b"WRONG_RECIPE", "railway.json": b"WRONG_CONFIG",
        ".env": b"PRIVATE_KEY", "src/.env": b"PRIVATE_KEY", "data/db.sqlite3": b"PRIVATE",
    }
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w") as archive:
        for name, value in contents.items():
            info = tarfile.TarInfo(name)
            info.size = len(value)
            archive.addfile(info, io.BytesIO(value))
            if build._include(name):
                path = tmp_path / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(value)
    return raw.getvalue(), source_fingerprint(tmp_path)


def test_archive_deterministic_and_contains_only_expected_sources(source):
    raw, fingerprint = source
    payload = build.package_archive(raw, fingerprint)
    assert payload == build.package_archive(raw, fingerprint)
    with tarfile.open(fileobj=io.BytesIO(payload), mode="r:gz") as archive:
        names = archive.getnames()
        assert "railway.json" not in names and ".env" not in names and "src/.env" not in names
        assert not any(name.startswith("data/") for name in names)
        assert archive.extractfile("Dockerfile").read() == b"FROM python:3.12-slim\n"
        assert archive.extractfile(".dockerignore").read() == b"**\n!src/**\n"
        assert all(m.isfile() and m.mtime == 0 for m in archive)


def test_mismatching_source_cannot_be_packaged(source):
    with pytest.raises(ValueError, match="source_mismatch"):
        build.package_archive(source[0], "0" * 64)


@pytest.mark.parametrize("name", ["../src/evil.py", "/src/evil.py", "scripts/.env",
                                 "src/secret.local", ".git/config", "Dockerfile", "railway.json",
                                 "", "src/..\\evil.py"])
def test_paths_and_non_sources_excluded(name):
    assert build._include(name) is False


def test_symlink_in_included_source_rejected():
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w") as archive:
        info = tarfile.TarInfo("src/evil.py")
        info.type = tarfile.SYMTYPE
        info.linkname = "/etc/passwd"
        archive.addfile(info)
    with pytest.raises(ValueError, match="archive_invalid"):
        build.package_archive(raw.getvalue(), "a" * 64)


def test_prepare_exact_commit_no_overwrite_or_network(source, tmp_path, monkeypatch):
    raw, fingerprint = source
    calls = []
    def archive(args, **kwargs):
        calls.append(args)
        return subprocess.CompletedProcess(args, 0, stdout=raw)
    monkeypatch.setattr(build.shutil, "which", lambda _: "git")
    monkeypatch.setattr(build.subprocess, "run", archive)
    output = tmp_path / "build.tar.gz"
    result = build.prepare(tmp_path, "a" * 40, fingerprint, output)
    assert calls == [["git", "archive", "--format=tar", "a" * 40]]
    assert result["uploaded"] is result["inference_started"] is False
    assert result["bytes"] == output.stat().st_size
    with pytest.raises(FileExistsError):
        build.prepare(tmp_path, "a" * 40, fingerprint, output)
    with pytest.raises(ValueError, match="identity_and_absolute"):
        build.prepare(tmp_path, "main", fingerprint, Path("relative"))
