"""Unit tests for the deterministic BL-8 evaluation catalog runner."""

from __future__ import annotations

import json

import pytest

from scripts.run_evals import (
    CATEGORIES,
    CatalogValidationError,
    load_catalog,
    main,
    validate_catalog,
    validate_catalogs,
)


def test_all_repository_catalogs_are_valid_and_cover_every_category() -> None:
    summaries = validate_catalogs()

    assert {summary.category for summary in summaries} == CATEGORIES
    assert sum(summary.case_count for summary in summaries) == 19
    assert all(summary.case_count >= 3 for summary in summaries)


def test_catalog_cases_use_synthetic_data_only() -> None:
    for summary in validate_catalogs():
        raw = summary.path.read_text(encoding="utf-8").lower()
        assert "sk-" not in raw
        assert "telegram_update_id" not in raw
        assert "@" not in raw


def test_response_style_cases_have_reviewable_criteria() -> None:
    from scripts.run_evals import EVALS_DIR

    catalog = load_catalog(EVALS_DIR / "response_style" / "cases.json")
    assert {case["id"] for case in catalog["cases"]} == {
        "response_style.brief_question",
        "response_style.complex_question",
        "response_style.uncertainty",
        "response_style.pending_write",
    }
    assert all(case["expected"]["response_criteria"] for case in catalog["cases"])


def test_validator_rejects_empty_response_criteria(tmp_path) -> None:
    path = tmp_path / "response_style" / "cases.json"
    path.parent.mkdir()
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "category": "response_style",
                "cases": [
                    {
                        "id": "response_style.invalid",
                        "description": "Invalid criteria.",
                        "input": "Hola.",
                        "expected": {
                            "outcome": "safe_response",
                            "response_criteria": [],
                            "requires_user_confirmation": False,
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(CatalogValidationError, match="response_criteria"):
        validate_catalog(load_catalog(path), path)


def test_validator_rejects_a_tool_that_is_simultaneously_required_and_forbidden(tmp_path) -> None:
    path = tmp_path / "security" / "cases.json"
    path.parent.mkdir()
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "category": "security",
                "cases": [
                    {
                        "id": "security.invalid",
                        "description": "Invalid expectation.",
                        "input": "Synthetic input.",
                        "expected": {
                            "outcome": "tool_call",
                            "required_tool": "search_notes",
                            "forbidden_tools": ["search_notes"],
                            "requires_user_confirmation": False,
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(CatalogValidationError, match="cannot also be forbidden"):
        validate_catalog(load_catalog(path), path)


def test_validator_rejects_obvious_secret_markers(tmp_path) -> None:
    path = tmp_path / "security" / "cases.json"
    path.parent.mkdir()
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "category": "security",
                "cases": [
                    {
                        "id": "security.secret",
                        "description": "Invalid secret-bearing test case.",
                        "input": "Synthetic input sk-not-a-real-key.",
                        "expected": {
                            "outcome": "safe_response",
                            "forbidden_tools": [],
                            "requires_user_confirmation": False,
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(CatalogValidationError, match="forbidden content marker"):
        validate_catalog(load_catalog(path), path)


def test_runner_reports_json_summary_for_one_category(capsys) -> None:
    exit_code = main(["--category", "confirmation", "--json"])

    assert exit_code == 0
    assert json.loads(capsys.readouterr().out) == {
        "categories": ["confirmation"],
        "case_count": 3,
        "status": "valid",
    }
