"""Export Git prompt content history for the read-only admin view (offline).

Run after prompt changes and commit the artifact. No Git or credentials in Railway.
No authors, emails, commit messages, deleted assets or files outside prompts/ exported.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.agent.prompt_catalog import HISTORY_PATH, PromptHistory, prompt_checksum  # noqa: E402


def git(root: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(root), *args]).decode("utf-8")


def build_history(root: Path) -> dict:
    files = git(root, "ls-tree", "-r", "--name-only", "HEAD", "--", "prompts/").splitlines()
    prompts = {}
    for name in files:
        if not name.startswith("prompts/") or not name.endswith(".md"):
            continue
        versions = []
        log = git(
            root,
            "log",
            "--format=%H%x09%cI",
            "--diff-filter=AM",
            "--no-renames",
            "HEAD",
            "--",
            name,
        )
        for entry in log.splitlines():
            revision, committed_at = entry.split("\t")
            content = git(root, "show", f"{revision}:{name}")
            versions.append(
                {
                    "revision": revision,
                    "committed_at": committed_at,
                    "sha256": prompt_checksum(content),
                    "content": content,
                }
            )
        prompts[name.removeprefix("prompts/")] = versions
    result = {
        "schema_version": 1,
        "source_revision": git(root, "log", "-1", "--format=%H", "HEAD", "--", "prompts/").strip(),
        "shallow": git(root, "rev-parse", "--is-shallow-repository").strip() == "true",
        "prompts": prompts,
    }
    PromptHistory.model_validate(result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Check artifact without writing")
    args = parser.parse_args()
    expected = build_history(ROOT)
    if args.check:
        try:
            actual = json.loads(HISTORY_PATH.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            actual = None
        if actual != expected:
            print("Prompt history missing/stale: run scripts/export_prompt_history.py")
            return 1
    else:
        HISTORY_PATH.write_text(
            json.dumps(expected, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    print(f"Prompt history checked/exported: {len(expected['prompts'])} assets")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
