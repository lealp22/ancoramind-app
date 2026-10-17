"""Prepare a private, root-Dockerfile eval archive from one committed tree.

Never uploads, deploys or executes inference. The explicit commit and external
fingerprint remain the identity; packaging does not assert GitHub deployment.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.eval_source import source_fingerprint  # noqa: E402


def _include(name: str) -> bool:
    path = PurePosixPath(name)
    if not path.parts or "\\" in name:
        return False
    if path.is_absolute() or ".." in path.parts or any(p.startswith(".") for p in path.parts):
        return name == "evals/Dockerfile.dockerignore"
    return (
        name in {"pyproject.toml", "README.md", "evals/Dockerfile", "evals/Dockerfile.dockerignore"}
        or (path.parts[0] in {"src", "scripts"} and path.suffix == ".py")
        or (path.parts[0] == "prompts" and path.suffix == ".md")
        or (path.parts[0] == "evals" and path.suffix == ".json")
    )


def package_archive(raw: bytes, fingerprint: str) -> bytes:
    """Copy allowlisted regular files only; root aliases are exact eval recipes."""
    files: dict[str, bytes] = {}
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:") as archive:
        for member in archive:
            if not _include(member.name) or member.isdir():
                continue
            if not member.isfile() or member.name in files:
                raise ValueError("eval_build_archive_invalid")
            stream = archive.extractfile(member)
            if stream is None:
                raise ValueError("eval_build_archive_invalid")
            files[member.name] = stream.read()
    for required in ("pyproject.toml", "README.md", "evals/Dockerfile",
                     "evals/Dockerfile.dockerignore", "scripts/eval_service.py"):
        if required not in files:
            raise ValueError("eval_build_archive_incomplete")
    with tempfile.TemporaryDirectory() as folder:
        for name, content in files.items():
            path = Path(folder) / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        if source_fingerprint(Path(folder)) != fingerprint:
            raise ValueError("eval_build_source_mismatch")
    files["Dockerfile"] = files["evals/Dockerfile"]
    files[".dockerignore"] = files["evals/Dockerfile.dockerignore"]
    output = io.BytesIO()
    with (
        gzip.GzipFile(fileobj=output, mode="wb", filename="", mtime=0) as compressed,
        tarfile.open(fileobj=compressed, mode="w", format=tarfile.USTAR_FORMAT) as archive,
    ):
        for name, content in sorted(files.items()):
            info = tarfile.TarInfo(name)
            info.size = len(content)
            info.mode = 0o644
            archive.addfile(info, io.BytesIO(content))
    return output.getvalue()


def prepare(root: Path, code_sha: str, fingerprint: str, output: Path) -> dict[str, object]:
    if (
        not re.fullmatch(r"[a-f0-9]{40}", code_sha)
        or not re.fullmatch(r"[a-f0-9]{64}", fingerprint)
        or not output.is_absolute()
    ):
        raise ValueError("eval_build_identity_and_absolute_output_required")
    git = shutil.which("git")
    if git is None:
        raise ValueError("eval_git_required")
    raw = subprocess.run(  # noqa: S603 - exact validated SHA, fixed Git archive, no shell
        [git, "archive", "--format=tar", code_sha], cwd=root,
        capture_output=True, timeout=30, check=True,
    ).stdout
    payload = package_archive(raw, fingerprint)
    with output.open("xb") as file:
        file.write(payload)
    return {"code_sha": code_sha, "source_fingerprint": fingerprint,
            "artifact_sha256": hashlib.sha256(payload).hexdigest(), "bytes": len(payload),
            "uploaded": False, "inference_started": False}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sha", required=True)
    parser.add_argument("--source-fingerprint", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        print(json.dumps(prepare(ROOT, args.sha, args.source_fingerprint, args.output)))
        return 0
    except (ValueError, OSError, tarfile.TarError, subprocess.SubprocessError):
        print(json.dumps({"status": "eval_build_blocked", "uploaded": False,
                          "inference_started": False}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
