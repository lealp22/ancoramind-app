"""No-network tests for the optional BL-8 T8 semantic-scoring preparation."""

from __future__ import annotations

import inspect
import json
from pathlib import Path

import pytest

import src.agent.eval_semantic_scoring as scoring_module
from scripts.run_evals import EVALS_DIR, load_catalog, validate_response_style_calibration_fixture
from src.agent.eval_semantic_scoring import (
    SemanticCaseScore,
    SemanticCriterionScore,
    SemanticJudgment,
    SemanticLabel,
    SemanticScoreKey,
    build_baseline,
    calibrate_judge,
    compare_to_baseline,
    load_calibration_labels,
    score_reply,
)
from src.domain.interactions.reply import AgentReply


def _criteria() -> dict[str, tuple[str, ...]]:
    catalog = load_catalog(EVALS_DIR / "response_style" / "cases.json")
    return {case["id"]: tuple(case["expected"]["response_criteria"]) for case in catalog["cases"]}


def _fixture() -> dict[str, object]:
    return json.loads(
        (EVALS_DIR / "response_style" / "provisional_labels.json").read_text(encoding="utf-8")
    )


class _FakeJudge:
    """Pure fake: records in-memory requests and never constructs an LLM client."""

    def __init__(self, labels: tuple[SemanticLabel, ...]) -> None:
        self._labels = labels
        self.requests = []

    async def judge(self, request):
        self.requests.append(request)
        return SemanticJudgment(
            label=self._labels[min(len(self.requests) - 1, len(self._labels) - 1)],
            judge_version="fake-judge-v1",
        )


def _score(case_id: str, status: str, *, revision: int = 7) -> SemanticCaseScore:
    key = SemanticScoreKey(
        logical_route="ancoramind-eval",
        config_revision=revision,
        rubric_version="response_style-v1",
        judge_version="fake-judge-v1",
    )
    label = {
        "passed": SemanticLabel.PASS,
        "failed": SemanticLabel.FAIL,
        "not_evaluated": SemanticLabel.NOT_EVALUATED,
    }[status]
    return SemanticCaseScore(
        case_id=case_id,
        key=key,
        criteria=(SemanticCriterionScore(criterion_index=0, label=label),),
    )


def test_semantic_scoring_module_has_no_runtime_inference_or_telemetry_imports() -> None:
    imports = [
        line
        for line in inspect.getsource(scoring_module).splitlines()
        if line.startswith(("import ", "from "))
    ]
    forbidden = ("llm_access", "openai", "httpx", "agno", "observability", "repositories")
    assert not any(any(name in line.lower() for name in forbidden) for line in imports)


def test_static_runner_validates_provisional_fixture_without_executing_a_judge() -> None:
    assert validate_response_style_calibration_fixture() == 9


async def test_provisional_labels_load_but_cannot_calibrate_an_external_judge() -> None:
    calibration = load_calibration_labels(_fixture(), response_style_cases=_criteria())

    assert calibration.label_source == "provisional_synthetic"
    assert len(calibration.examples) == 9
    with pytest.raises(ValueError, match="human_reviewed"):
        await calibrate_judge(
            calibration, response_style_cases=_criteria(), judge=_FakeJudge((SemanticLabel.PASS,))
        )


async def test_human_reviewed_fixture_calibrates_per_selected_criterion_only() -> None:
    raw = _fixture()
    raw["label_source"] = "human_reviewed"
    calibration = load_calibration_labels(raw, response_style_cases=_criteria())
    expected_count = sum(
        1
        for example in calibration.examples
        for label in example.labels
        if label is not SemanticLabel.AMBIGUOUS
    )
    judge = _FakeJudge(tuple(SemanticLabel.PASS for _ in range(expected_count)))

    result = await calibrate_judge(calibration, response_style_cases=_criteria(), judge=judge)

    assert len(judge.requests) == expected_count
    assert result.compared_count == expected_count
    assert result.skipped_ambiguous_count == 2
    assert result.not_evaluated_count == 0
    assert "Una lista de tareas" not in str(result.metadata())


async def test_score_is_per_criterion_and_report_excludes_reply_and_criteria() -> None:
    reply = AgentReply(answer="Respuesta sintética privada.", proposal_text="Propuesta privada.")
    judge = _FakeJudge((SemanticLabel.PASS, SemanticLabel.NOT_EVALUATED))

    score = await score_reply(
        case_id="response_style.synthetic",
        response_criteria=("Primer criterio privado.", "Segundo criterio privado."),
        reply=reply,
        logical_route="ancoramind-eval",
        config_revision=7,
        rubric_version="response_style-v1",
        judge=judge,
    )

    assert score.status == "not_evaluated"
    assert [item.criterion_index for item in score.criteria] == [0, 1]
    serialized = str(score.metadata())
    assert "Respuesta sintética privada" not in serialized
    assert "Propuesta privada" not in serialized
    assert "Primer criterio privado" not in serialized


def test_baseline_requires_identical_versioned_key_and_reports_only_status_deltas() -> None:
    baseline = build_baseline(
        (_score("response_style.a", "passed"), _score("response_style.b", "failed"))
    )
    current = (_score("response_style.a", "failed"), _score("response_style.b", "passed"))

    comparison = compare_to_baseline(baseline, current)

    assert comparison.regressed_case_ids == ("response_style.a",)
    assert comparison.improved_case_ids == ("response_style.b",)
    assert comparison.newly_not_evaluated_case_ids == ()
    assert "respuesta" not in str(comparison.metadata()).lower()
    with pytest.raises(ValueError, match="identical versioned key"):
        compare_to_baseline(baseline, (_score("response_style.a", "passed", revision=8),))


def test_label_fixture_rejects_a_nonsemantic_criterion_index() -> None:
    raw = _fixture()
    example = raw["examples"][0]
    assert isinstance(example, dict)
    example["criterion_indices"] = [99]

    with pytest.raises(ValueError, match="criterion_indices"):
        load_calibration_labels(raw, response_style_cases=_criteria())


def test_semantic_calibration_file_stays_synthetic_and_without_obvious_secrets() -> None:
    raw = (
        Path(EVALS_DIR / "response_style" / "provisional_labels.json")
        .read_text(encoding="utf-8")
        .lower()
    )
    assert "sk-" not in raw
    assert "@" not in raw
