"""Code identity for a Git checkout or an explicitly sealed eval image.

The seal is not a signature or proof of a clean Git checkout. Live approval must
compare it with a clean, CI-checked checkout outside the image. No Git metadata,
credentials or history need to be copied into the runtime container.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path

MANIFEST = ".eval-source.json"


def source_fingerprint(root: Path) -> str:
    """Hash executable sources, rubric and image recipe, normalizing CRLF only."""
    paths: set[Path] = set()
    for folder, pattern in (("src", "*.py"), ("scripts", "*.py"),
                            ("prompts", "*.md"), ("evals", "*.json")):
        paths.update((root / folder).rglob(pattern))
    for name in ("pyproject.toml", "evals/Dockerfile", "evals/Dockerfile.dockerignore"):
        path = root / name
        if path.is_file():
            paths.add(path)
    digest = hashlib.sha256()
    for path in sorted(paths, key=lambda item: item.relative_to(root).as_posix()):
        if path.is_symlink():
            raise ValueError("eval_source_symlink_forbidden")
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(b"\0")
        digest.update(path.read_text(encoding="utf-8").replace("\r\n", "\n").encode())
        digest.update(b"\0")
    return digest.hexdigest()


def source_identity(root: Path) -> dict[str, str]:
    """Never trust a baked SHA without matching the approved source fingerprint."""
    fingerprint = source_fingerprint(root)
    if not (root / ".git").exists():
        manifest = json.loads((root / MANIFEST).read_text(encoding="utf-8"))
        if (
            not isinstance(manifest, dict)
            or set(manifest) != {"version", "code_sha", "source_fingerprint"}
            or manifest["version"] != 1
            or not isinstance(manifest["code_sha"], str)
            or not re.fullmatch(r"[a-f0-9]{40}", manifest["code_sha"])
            or manifest["source_fingerprint"] != fingerprint
        ):
            raise ValueError("eval_image_provenance_mismatch")
        return {"code_sha": manifest["code_sha"], "source_fingerprint": fingerprint,
                "worktree": "clean", "identity_source": "sealed_image"}
    git = shutil.which("git")
    if git is None:
        raise ValueError("eval_git_required")
    sha = subprocess.run(  # noqa: S603 - fixed Git subcommand, no shell
        [git, "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True,
        timeout=10, check=True,
    ).stdout.strip()
    dirty = subprocess.run(  # noqa: S603 - fixed Git subcommand, no shell
        [git, "status", "--porcelain"], cwd=root, capture_output=True, text=True,
        timeout=10, check=True,
    ).stdout.strip()
    return {"code_sha": sha, "source_fingerprint": fingerprint,
            "worktree": "dirty" if dirty else "clean", "identity_source": "git"}


def seal_image(root: Path, code_sha: str, fingerprint: str) -> None:
    """Build-only seal: require external identity and exact packaged content."""
    if (
        not re.fullmatch(r"[a-f0-9]{40}", code_sha)
        or not re.fullmatch(r"[a-f0-9]{64}", fingerprint)
        or source_fingerprint(root) != fingerprint
        or (root / ".git").exists()
    ):
        raise ValueError("eval_image_build_identity_required")
    with (root / MANIFEST).open("x", encoding="utf-8") as file:
        json.dump({"version": 1, "code_sha": code_sha, "source_fingerprint": fingerprint}, file)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--code-sha", required=True)
    parser.add_argument("--source-fingerprint", required=True)
    args = parser.parse_args()
    seal_image(Path(__file__).resolve().parents[1], args.code_sha, args.source_fingerprint)
