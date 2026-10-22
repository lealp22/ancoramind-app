"""Read-only inventory of packaged prompt assets, not an activation registry.

No Git process, network, DB, provider or application startup is needed at runtime.
History is an explicitly exported artifact; current files remain the source of truth.
"""

from __future__ import annotations

import ast
import hashlib
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from src.agent.instructions import PROMPTS_DIR

ROOT = Path(__file__).resolve().parents[2]
HISTORY_PATH = Path(__file__).with_name("prompt_history.json")
MAX_PROMPT_BYTES = 262144
MAX_HISTORY_BYTES = 5 * 1024 * 1024


def prompt_checksum(content: str) -> str:
    """Hash the text the loader consumes: universal newlines and strip(), UTF-8."""
    normalized = content.replace("\r\n", "\n").replace("\r", "\n").strip()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


class PromptVersion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    revision: str = Field(pattern=r"^[0-9a-f]{40}$")
    committed_at: str
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    content: str


class PromptHistory(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = Field(ge=1, le=1)
    source_revision: str = Field(pattern=r"^[0-9a-f]{40}$")
    shallow: bool
    prompts: dict[str, list[PromptVersion]]


def _regular_asset(path: Path, root: Path) -> bool:
    """Never follow a symlink, including symlinked ancestor directories."""
    return (
        path.is_relative_to(root)
        and not any(part.is_symlink() for part in (path, *path.parents))
        and path.is_file()
    )


class PromptCatalog:
    def __init__(
        self,
        prompts_dir: Path = PROMPTS_DIR,
        source_dir: Path = ROOT / "src",
        history_path: Path = HISTORY_PATH,
    ) -> None:
        self.prompts_dir = prompts_dir.absolute()
        self.source_dir = source_dir.absolute()
        self.history_path = history_path

    def _files(self) -> dict[str, Path]:
        return {
            path.relative_to(self.prompts_dir).as_posix(): path
            for path in sorted(self.prompts_dir.rglob("*.md"))
            if _regular_asset(path, self.prompts_dir) and path.stat().st_size <= MAX_PROMPT_BYTES
        }

    def _history(self) -> tuple[PromptHistory | None, str]:
        try:
            if (
                self.history_path.is_symlink()
                or self.history_path.stat().st_size > MAX_HISTORY_BYTES
            ):
                return None, "invalid"
            history = PromptHistory.model_validate_json(self.history_path.read_bytes())
            for versions in history.prompts.values():
                if len({v.revision for v in versions}) != len(versions):
                    return None, "invalid"
                if any(prompt_checksum(v.content) != v.sha256 for v in versions):
                    return None, "invalid"
            return history, "available"
        except FileNotFoundError:
            return None, "unavailable"
        except (OSError, ValueError):
            return None, "invalid"

    def _usages(self) -> tuple[dict[str, list[dict[str, Any]]], bool]:
        usages: dict[str, list[dict[str, Any]]] = {}
        complete = self.source_dir.is_dir()
        for path in sorted(self.source_dir.rglob("*.py")):
            if not _regular_asset(path, self.source_dir):
                continue
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, SyntaxError):
                complete = False
                continue
            for node in ast.walk(tree):
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                    and node.func.id == "load_prompt"
                    and node.args
                    and isinstance(node.args[0], ast.Constant)
                    and isinstance(node.args[0].value, str)
                ):
                    usages.setdefault(node.args[0].value, []).append(
                        {
                            "source": "src/" + path.relative_to(self.source_dir).as_posix(),
                            "line": node.lineno,
                        }
                    )
        return usages, complete

    def inventory(self) -> dict[str, Any]:
        history, state = self._history()
        usages, complete = self._usages()
        entries = []
        for name, path in self._files().items():
            checksum = prompt_checksum(path.read_text(encoding="utf-8"))
            versions = history.prompts.get(name, []) if history else []
            entries.append(
                {
                    "path": name,
                    "sha256": checksum,
                    "usages": usages.get(name, []),
                    "version_count": len(versions),
                    "matches_latest_export": checksum == versions[0].sha256 if versions else None,
                }
            )
        return {
            "prompts": entries,
            "history_status": state,
            "history_source_revision": history.source_revision if history else None,
            "history_shallow": history.shallow if history else None,
            "usage_scan_complete": complete,
        }

    def detail(self, name: str, revision: str | None = None) -> dict[str, Any]:
        # Lookup, not a join with a user-supplied path. No arbitrary filesystem reads.
        files = self._files()
        if name not in files:
            raise KeyError(name)
        history, state = self._history()
        versions = history.prompts.get(name, []) if history else []
        if revision is None:
            content = files[name].read_text(encoding="utf-8")
        else:
            version = next((v for v in versions if v.revision == revision), None)
            if version is None:
                raise KeyError(revision)
            content = version.content
        return {
            "path": name,
            "revision": revision,
            "sha256": prompt_checksum(content),
            "content": content,
            "history_status": state,
            "versions": [v.model_dump(exclude={"content"}) for v in versions],
        }
