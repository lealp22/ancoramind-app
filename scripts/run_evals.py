"""Validate AncoraMind's versioned agent-evaluation catalogs.

This first BL-8 increment is deliberately deterministic: it validates the
structure and coverage of the cases stored in ``evals/`` but never sends user
content to an LLM or invokes application tools. A future runner can consume the
same catalog format to evaluate a governed Agent run.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

EVALS_DIR = Path(__file__).resolve().parent.parent / "evals"
CATEGORIES = frozenset({"confirmation", "documents", "security", "tool_selection", "vehicle"})
OUTCOMES = frozenset({"clarify", "confirm_pending_action", "safe_response", "tool_call"})
FORBIDDEN_CONTENT_MARKERS = ("sk-", "authorization: bearer", "begin private key")


class CatalogValidationError(ValueError):
    """Raised when an evaluation catalog does not satisfy the version-1 contract."""


@dataclass(frozen=True)
class CatalogSummary:
    """A validated catalog and the number of cases it contains."""

    category: str
    path: Path
    case_count: int


def discover_catalog_paths(evals_dir: Path = EVALS_DIR) -> list[Path]:
    """Return catalog paths in the stable category order used by the repository."""
    return [evals_dir / category / "cases.json" for category in sorted(CATEGORIES)]


def load_catalog(path: Path) -> dict[str, Any]:
    """Load one JSON catalog, preserving a clear error for malformed JSON."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise CatalogValidationError(f"Catalog missing: {path}") from error
    except json.JSONDecodeError as error:
        raise CatalogValidationError(f"Invalid JSON in {path}: {error.msg}") from error

    if not isinstance(raw, dict):
        raise CatalogValidationError(f"Catalog root must be an object: {path}")
    return raw


def _require_string(value: object, field: str, case_id: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CatalogValidationError(f"{case_id}: {field} must be a non-empty string")
    return value


def _validate_expected(expected: object, case_id: str) -> None:
    if not isinstance(expected, dict):
        raise CatalogValidationError(f"{case_id}: expected must be an object")

    outcome = expected.get("outcome")
    if outcome not in OUTCOMES:
        allowed = ", ".join(sorted(OUTCOMES))
        raise CatalogValidationError(f"{case_id}: expected.outcome must be one of: {allowed}")

    required_tool = expected.get("required_tool")
    if outcome in {"confirm_pending_action", "tool_call"}:
        _require_string(required_tool, "expected.required_tool", case_id)
    elif required_tool is not None:
        raise CatalogValidationError(
            f"{case_id}: expected.required_tool is only valid for tool_call or "
            "confirm_pending_action"
        )

    forbidden_tools = expected.get("forbidden_tools", [])
    if not isinstance(forbidden_tools, list) or not all(
        isinstance(tool, str) and tool.strip() for tool in forbidden_tools
    ):
        raise CatalogValidationError(f"{case_id}: expected.forbidden_tools must be a list of names")

    if required_tool is not None and required_tool in forbidden_tools:
        raise CatalogValidationError(f"{case_id}: required_tool cannot also be forbidden")

    confirmation = expected.get("requires_user_confirmation")
    if not isinstance(confirmation, bool):
        raise CatalogValidationError(
            f"{case_id}: expected.requires_user_confirmation must be boolean"
        )


def _validate_catalog_content(catalog: dict[str, Any], path: Path) -> None:
    """Reject obvious secret markers from versioned synthetic test data."""
    serialized = json.dumps(catalog, ensure_ascii=False).lower()
    for marker in FORBIDDEN_CONTENT_MARKERS:
        if marker in serialized:
            raise CatalogValidationError(
                f"{path}: catalog contains forbidden content marker '{marker}'"
            )


def validate_catalog(catalog: dict[str, Any], path: Path) -> CatalogSummary:
    """Validate the version-1 static evaluation contract for one catalog."""
    _validate_catalog_content(catalog, path)
    category = catalog.get("category")
    if category not in CATEGORIES:
        allowed_categories = ", ".join(sorted(CATEGORIES))
        raise CatalogValidationError(f"{path}: category must be one of: {allowed_categories}")
    if path.parent.name != category:
        raise CatalogValidationError(
            f"{path}: category must match its parent directory ({path.parent.name})"
        )
    if catalog.get("schema_version") != 1:
        raise CatalogValidationError(f"{path}: schema_version must be 1")

    cases = catalog.get("cases")
    if not isinstance(cases, list) or not cases:
        raise CatalogValidationError(f"{path}: cases must be a non-empty list")

    case_ids: set[str] = set()
    for index, case in enumerate(cases, start=1):
        if not isinstance(case, dict):
            raise CatalogValidationError(f"{path}: case {index} must be an object")
        case_id = _require_string(case.get("id"), "id", f"case {index}")
        if case_id in case_ids:
            raise CatalogValidationError(f"{path}: duplicate case id: {case_id}")
        case_ids.add(case_id)
        if not case_id.startswith(f"{category}."):
            raise CatalogValidationError(f"{case_id}: id must start with '{category}.'")

        _require_string(case.get("description"), "description", case_id)
        _require_string(case.get("input"), "input", case_id)
        _validate_expected(case.get("expected"), case_id)

        tags = case.get("tags", [])
        valid_tags = isinstance(tags, list) and all(
            isinstance(tag, str) and tag.strip() for tag in tags
        )
        if not valid_tags:
            raise CatalogValidationError(f"{case_id}: tags must be a list of non-empty strings")

        context = case.get("context", {})
        if not isinstance(context, dict):
            raise CatalogValidationError(f"{case_id}: context must be an object")

    return CatalogSummary(category=category, path=path, case_count=len(cases))


def validate_catalogs(
    evals_dir: Path = EVALS_DIR, categories: set[str] | None = None
) -> list[CatalogSummary]:
    """Load and validate every selected catalog, failing on missing categories."""
    selected = CATEGORIES if categories is None else categories
    unknown = selected - CATEGORIES
    if unknown:
        raise CatalogValidationError(f"Unknown categories: {', '.join(sorted(unknown))}")

    summaries: list[CatalogSummary] = []
    for path in discover_catalog_paths(evals_dir):
        if path.parent.name in selected:
            summaries.append(validate_catalog(load_catalog(path), path))
    return summaries


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser without doing I/O, keeping it easy to test."""
    parser = argparse.ArgumentParser(
        description="Validate AncoraMind static agent-evaluation catalogs."
    )
    parser.add_argument(
        "--category",
        action="append",
        choices=sorted(CATEGORIES),
        help="Validate only one category; may be repeated.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the validation summary as JSON.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run static validation and return a process status code."""
    args = build_parser().parse_args(argv)
    categories = set(args.category) if args.category else None

    try:
        summaries = validate_catalogs(categories=categories)
    except CatalogValidationError as error:
        print(f"Evals validation failed: {error}", file=sys.stderr)
        return 1

    total = sum(summary.case_count for summary in summaries)
    if args.json:
        print(
            json.dumps(
                {
                    "categories": [summary.category for summary in summaries],
                    "case_count": total,
                    "status": "valid",
                },
                ensure_ascii=False,
            )
        )
    else:
        print(f"Evals catalog valid: {total} cases across {len(summaries)} categories.")
        for summary in summaries:
            print(f"- {summary.category}: {summary.case_count} cases")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
