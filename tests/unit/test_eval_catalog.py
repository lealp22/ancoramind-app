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
    assert sum(summary.case_count for summary in summaries) == 59
    assert all(summary.case_count >= 3 for summary in summaries)


def test_catalog_cases_use_synthetic_data_only() -> None:
    for summary in validate_catalogs():
        raw = summary.path.read_text(encoding="utf-8").lower()
        assert "sk-" not in raw
        assert "telegram_update_id" not in raw
        assert "@" not in raw


def test_security_catalog_covers_attack_and_benign_fixtures() -> None:
    from scripts.run_evals import EVALS_DIR

    cases = load_catalog(EVALS_DIR / "security" / "cases.json")["cases"]
    assert len(cases) == 31
    assert sum("benign_control" in case["tags"] for case in cases) == 9
    assert sum("injection_variant" in case["tags"] for case in cases) == 8
    assert {"unicode", "encoding", "link", "multimodal_description", "web"}.issubset(
        {tag for case in cases for tag in case["tags"]}
    )
    for case in cases:
        if "benign_control" in case["tags"]:
            assert case["expected"]["required_tool"] in {
                "get_document",
                "search_notes",
                "search_web",
            }


def test_web_security_cases_require_search_web_and_forbid_acting_on_results() -> None:
    from scripts.run_evals import EVALS_DIR

    cases = load_catalog(EVALS_DIR / "security" / "cases.json")["cases"]
    web_attacks = [
        case for case in cases if "web" in case["tags"] and "benign_control" not in case["tags"]
    ]

    assert len(web_attacks) == 5
    for case in web_attacks:
        assert case["expected"]["required_tool"] == "search_web"
        assert case["expected"]["forbidden_tools"]
        assert "prompt_injection" in case["tags"]


def test_response_style_cases_have_reviewable_criteria() -> None:
    from scripts.run_evals import EVALS_DIR

    catalog = load_catalog(EVALS_DIR / "response_style" / "cases.json")
    assert {case["id"] for case in catalog["cases"]} == {
        "response_style.brief_question",
        "response_style.complex_question",
        "response_style.uncertainty",
        "response_style.pending_write",
        "response_style.single_proposal",
        "response_style.mixed_read_proposal",
        "response_style.tasks_after_discard",
        "response_style.explicit_reproposal",
        "response_style.pending_proposals_read",
        "response_style.document_normal_reference",
        "response_style.document_explicit_id",
        "response_style.document_duplicate_names",
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
        "case_count": 7,
        "semantic_calibration_example_count": 9,
        "status": "valid",
    }
