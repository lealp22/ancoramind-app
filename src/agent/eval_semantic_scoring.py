"""Optional, in-memory semantic scoring contracts for BL-8 T8.

This module deliberately has no provider, LLMAccess, network, telemetry, CLI,
or persistence wiring. It prepares the typed boundary that a future governed
judge adapter may implement only after explicit T7 cost and privacy approval.
Raw synthetic replies and criteria stay in memory; all exported projections are
metadata-only.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from src.domain.interactions.reply import AgentReply


class SemanticLabel(StrEnum):
    """Human or judge assessment for one concrete response criterion."""

    PASS = "pass"  # noqa: S105 - enum label, not a credential
    FAIL = "fail"
    AMBIGUOUS = "ambiguous"
    NOT_EVALUATED = "not_evaluated"


@dataclass(frozen=True)
class SemanticJudgeRequest:
    """One criterion and synthetic reply held only during an optional judgment."""

    case_id: str
    criterion_index: int
    criterion: str
    reply: AgentReply


@dataclass(frozen=True)
class SemanticJudgment:
    """One judge result; ``NOT_EVALUATED`` is never a passing result."""

    label: SemanticLabel
    judge_version: str


class SemanticJudge(Protocol):
    """Optional adapter port; future implementations must remain governed."""

    async def judge(self, request: SemanticJudgeRequest) -> SemanticJudgment: ...


@dataclass(frozen=True)
class SemanticCriterionScore:
    """In-memory judgment result for one criterion, without reportable text."""

    criterion_index: int
    label: SemanticLabel

    def metadata(self) -> dict[str, object]:
        return {"criterion_index": self.criterion_index, "label": self.label.value}


@dataclass(frozen=True)
class SemanticScoreKey:
    """Versioned identity required to compare semantic scores safely."""

    logical_route: str
    config_revision: int
    rubric_version: str
    judge_version: str


@dataclass(frozen=True)
class SemanticCaseScore:
    """Per-case scoring result; reply and criteria never leave this object."""

    case_id: str
    key: SemanticScoreKey
    criteria: tuple[SemanticCriterionScore, ...]

    @property
    def status(self) -> str:
        if any(score.label is SemanticLabel.NOT_EVALUATED for score in self.criteria):
            return "not_evaluated"
        return (
            "passed"
            if all(score.label is SemanticLabel.PASS for score in self.criteria)
            else "failed"
        )

    def metadata(self) -> dict[str, object]:
        return {
            "case_id": self.case_id,
            "logical_route": self.key.logical_route,
            "config_revision": self.key.config_revision,
            "rubric_version": self.key.rubric_version,
            "judge_version": self.key.judge_version,
            "status": self.status,
            "criteria": [score.metadata() for score in self.criteria],
        }


@dataclass(frozen=True)
class CalibrationLabeledReply:
    """Synthetic reply plus review labels held only for optional calibration."""

    example_id: str
    case_id: str
    reply: AgentReply
    criterion_indices: tuple[int, ...]
    labels: tuple[SemanticLabel, ...]


@dataclass(frozen=True)
class SemanticCalibrationSet:
    """Validated labels for a subset of response-style cases.

    ``label_source`` distinguishes provisional synthetic examples from labels
    that a human reviewer has explicitly approved. Only the latter may calibrate
    an external semantic judge.
    """

    rubric_version: str
    label_source: str
    examples: tuple[CalibrationLabeledReply, ...]


@dataclass(frozen=True)
class CalibrationResult:
    """Metadata-only agreement summary; ambiguous human labels are excluded."""

    rubric_version: str
    judge_version: str
    compared_count: int
    agreement_count: int
    disagreement_count: int
    skipped_ambiguous_count: int
    not_evaluated_count: int

    def metadata(self) -> dict[str, object]:
        return {
            "rubric_version": self.rubric_version,
            "judge_version": self.judge_version,
            "compared_count": self.compared_count,
            "agreement_count": self.agreement_count,
            "disagreement_count": self.disagreement_count,
            "skipped_ambiguous_count": self.skipped_ambiguous_count,
            "not_evaluated_count": self.not_evaluated_count,
        }


@dataclass(frozen=True)
class SemanticBaseline:
    """In-memory baseline for exactly one route/configuration/rubric/judge key."""

    key: SemanticScoreKey
    cases: tuple[SemanticCaseScore, ...]

    def metadata(self) -> dict[str, object]:
        return {
            "logical_route": self.key.logical_route,
            "config_revision": self.key.config_revision,
            "rubric_version": self.key.rubric_version,
            "judge_version": self.key.judge_version,
            "case_count": len(self.cases),
            "statuses": {case.case_id: case.status for case in self.cases},
        }


@dataclass(frozen=True)
class BaselineComparison:
    """Metadata-only delta against a compatible baseline."""

    key: SemanticScoreKey
    compared_case_count: int
    regressed_case_ids: tuple[str, ...]
    improved_case_ids: tuple[str, ...]
    unchanged_case_ids: tuple[str, ...]
    newly_not_evaluated_case_ids: tuple[str, ...]

    def metadata(self) -> dict[str, object]:
        return {
            "logical_route": self.key.logical_route,
            "config_revision": self.key.config_revision,
            "rubric_version": self.key.rubric_version,
            "judge_version": self.key.judge_version,
            "compared_case_count": self.compared_case_count,
            "regressed_case_ids": list(self.regressed_case_ids),
            "improved_case_ids": list(self.improved_case_ids),
            "unchanged_case_ids": list(self.unchanged_case_ids),
            "newly_not_evaluated_case_ids": list(self.newly_not_evaluated_case_ids),
        }


async def score_reply(
    *,
    case_id: str,
    response_criteria: Sequence[str],
    reply: AgentReply,
    logical_route: str,
    config_revision: int,
    rubric_version: str,
    judge: SemanticJudge,
) -> SemanticCaseScore:
    """Score each criterion independently without exporting the synthetic reply."""

    _validate_score_identity(
        case_id=case_id,
        response_criteria=response_criteria,
        logical_route=logical_route,
        config_revision=config_revision,
        rubric_version=rubric_version,
    )
    scores: list[SemanticCriterionScore] = []
    judge_versions: set[str] = set()
    for index, criterion in enumerate(response_criteria):
        judgment = await judge.judge(
            SemanticJudgeRequest(
                case_id=case_id,
                criterion_index=index,
                criterion=criterion,
                reply=reply,
            )
        )
        if judgment.label is SemanticLabel.AMBIGUOUS:
            raise ValueError("semantic judges must return pass, fail, or not_evaluated")
        if not judgment.judge_version.strip():
            raise ValueError("semantic judge version must be non-empty")
        judge_versions.add(judgment.judge_version)
        scores.append(SemanticCriterionScore(criterion_index=index, label=judgment.label))
    if len(judge_versions) != 1:
        raise ValueError("one score_reply call must use exactly one judge version")
    return SemanticCaseScore(
        case_id=case_id,
        key=SemanticScoreKey(
            logical_route=logical_route,
            config_revision=config_revision,
            rubric_version=rubric_version,
            judge_version=next(iter(judge_versions)),
        ),
        criteria=tuple(scores),
    )


def load_calibration_labels(
    raw: object,
    *,
    response_style_cases: Mapping[str, Sequence[str]],
) -> SemanticCalibrationSet:
    """Validate human synthetic labels against the response-style catalog contract."""

    if not isinstance(raw, Mapping):
        raise ValueError("semantic calibration root must be an object")
    if raw.get("schema_version") != 1:
        raise ValueError("semantic calibration schema_version must be 1")
    rubric_version = raw.get("rubric_version")
    if not isinstance(rubric_version, str) or not rubric_version.strip():
        raise ValueError("semantic calibration rubric_version must be a non-empty string")
    label_source = raw.get("label_source")
    if label_source not in {"human_reviewed", "provisional_synthetic"}:
        raise ValueError("semantic calibration label_source is invalid")
    examples = raw.get("examples")
    if not isinstance(examples, list) or not examples:
        raise ValueError("semantic calibration examples must be a non-empty list")

    seen_ids: set[str] = set()
    materialized: list[CalibrationLabeledReply] = []
    for raw_example in examples:
        if not isinstance(raw_example, Mapping):
            raise ValueError("semantic calibration example must be an object")
        example_id = _require_string(raw_example.get("id"), "semantic calibration example id")
        if example_id in seen_ids:
            raise ValueError(f"duplicate semantic calibration example id: {example_id}")
        seen_ids.add(example_id)
        case_id = _require_string(raw_example.get("case_id"), f"{example_id}: case_id")
        criteria = response_style_cases.get(case_id)
        if criteria is None:
            raise ValueError(f"{example_id}: case_id is not a response_style case")
        reply = _reply_from_raw(raw_example.get("reply"), example_id)
        criterion_indices = raw_example.get("criterion_indices")
        if (
            not isinstance(criterion_indices, list)
            or not criterion_indices
            or not all(
                isinstance(index, int) and not isinstance(index, bool)
                for index in criterion_indices
            )
            or len(set(criterion_indices)) != len(criterion_indices)
            or any(index < 0 or index >= len(criteria) for index in criterion_indices)
        ):
            raise ValueError(
                f"{example_id}: criterion_indices must select unique response criteria"
            )
        labels = raw_example.get("labels")
        if not isinstance(labels, list) or len(labels) != len(criterion_indices):
            raise ValueError(f"{example_id}: labels must match criterion_indices length")
        parsed_labels: list[SemanticLabel] = []
        for label in labels:
            try:
                parsed = SemanticLabel(label)
            except (TypeError, ValueError) as error:
                raise ValueError(f"{example_id}: invalid human label") from error
            if parsed is SemanticLabel.NOT_EVALUATED:
                raise ValueError(f"{example_id}: calibration labels cannot be not_evaluated")
            parsed_labels.append(parsed)
        materialized.append(
            CalibrationLabeledReply(
                example_id=example_id,
                case_id=case_id,
                reply=reply,
                criterion_indices=tuple(criterion_indices),
                labels=tuple(parsed_labels),
            )
        )
    return SemanticCalibrationSet(
        rubric_version=rubric_version,
        label_source=label_source,
        examples=tuple(
            materialized,
        ),
    )


async def calibrate_judge(
    calibration: SemanticCalibrationSet,
    *,
    response_style_cases: Mapping[str, Sequence[str]],
    judge: SemanticJudge,
) -> CalibrationResult:
    """Compare an injected judge to human labels; ambiguous labels never inflate agreement."""

    if calibration.label_source != "human_reviewed":
        raise ValueError("semantic calibration requires human_reviewed labels")
    compared = agreement = disagreement = skipped_ambiguous = not_evaluated = 0
    judge_versions: set[str] = set()
    for example in calibration.examples:
        criteria = response_style_cases[example.case_id]
        for index, human_label in zip(example.criterion_indices, example.labels, strict=True):
            if human_label is SemanticLabel.AMBIGUOUS:
                skipped_ambiguous += 1
                continue
            criterion = criteria[index]
            judgment = await judge.judge(
                SemanticJudgeRequest(
                    case_id=example.case_id,
                    criterion_index=index,
                    criterion=criterion,
                    reply=example.reply,
                )
            )
            if not judgment.judge_version.strip():
                raise ValueError("semantic judge version must be non-empty")
            judge_versions.add(judgment.judge_version)
            if judgment.label is SemanticLabel.NOT_EVALUATED:
                not_evaluated += 1
                continue
            if judgment.label is SemanticLabel.AMBIGUOUS:
                raise ValueError("semantic judges must return pass, fail, or not_evaluated")
            compared += 1
            if judgment.label is human_label:
                agreement += 1
            else:
                disagreement += 1
    if len(judge_versions) != 1:
        raise ValueError("one calibration run must use exactly one judge version")
    return CalibrationResult(
        rubric_version=calibration.rubric_version,
        judge_version=next(iter(judge_versions)),
        compared_count=compared,
        agreement_count=agreement,
        disagreement_count=disagreement,
        skipped_ambiguous_count=skipped_ambiguous,
        not_evaluated_count=not_evaluated,
    )


def build_baseline(scores: Sequence[SemanticCaseScore]) -> SemanticBaseline:
    """Create an in-memory baseline; content-free metadata may be exported separately."""

    if not scores:
        raise ValueError("semantic baseline requires at least one case score")
    key = scores[0].key
    if any(score.key != key for score in scores):
        raise ValueError("semantic baseline scores must share one versioned key")
    if len({score.case_id for score in scores}) != len(scores):
        raise ValueError("semantic baseline case ids must be unique")
    return SemanticBaseline(key=key, cases=tuple(scores))


def compare_to_baseline(
    baseline: SemanticBaseline, current: Sequence[SemanticCaseScore]
) -> BaselineComparison:
    """Compare compatible score statuses without exposing replies or criteria."""

    if any(score.key != baseline.key for score in current):
        raise ValueError("semantic baseline comparison requires an identical versioned key")
    previous = {score.case_id: score.status for score in baseline.cases}
    current_by_id = {score.case_id: score.status for score in current}
    if len(current_by_id) != len(current):
        raise ValueError("semantic baseline comparison case ids must be unique")
    shared_ids = tuple(sorted(set(previous).intersection(current_by_id)))
    regressed: list[str] = []
    improved: list[str] = []
    unchanged: list[str] = []
    newly_not_evaluated: list[str] = []
    for case_id in shared_ids:
        before, after = previous[case_id], current_by_id[case_id]
        if after == "not_evaluated" and before != "not_evaluated":
            newly_not_evaluated.append(case_id)
        elif before == after:
            unchanged.append(case_id)
        elif before == "passed" and after == "failed":
            regressed.append(case_id)
        elif before == "failed" and after == "passed":
            improved.append(case_id)
        else:
            unchanged.append(case_id)
    return BaselineComparison(
        key=baseline.key,
        compared_case_count=len(shared_ids),
        regressed_case_ids=tuple(regressed),
        improved_case_ids=tuple(improved),
        unchanged_case_ids=tuple(unchanged),
        newly_not_evaluated_case_ids=tuple(newly_not_evaluated),
    )


def _validate_score_identity(
    *,
    case_id: str,
    response_criteria: Sequence[str],
    logical_route: str,
    config_revision: int,
    rubric_version: str,
) -> None:
    _require_string(case_id, "case_id")
    _require_string(logical_route, "logical_route")
    _require_string(rubric_version, "rubric_version")
    if config_revision < 0:
        raise ValueError("config_revision must be non-negative")
    if not response_criteria or not all(
        isinstance(item, str) and item.strip() for item in response_criteria
    ):
        raise ValueError("response_criteria must be a non-empty sequence of strings")


def _reply_from_raw(value: object, example_id: str) -> AgentReply:
    if not isinstance(value, Mapping):
        raise ValueError(f"{example_id}: reply must be an object")
    answer = value.get("answer")
    proposal_text = value.get("proposal_text")
    if not isinstance(answer, str) or not isinstance(proposal_text, str):
        raise ValueError(f"{example_id}: reply.answer and reply.proposal_text must be strings")
    return AgentReply(answer=answer, proposal_text=proposal_text)


def _require_string(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value


__all__ = [
    "BaselineComparison",
    "CalibrationResult",
    "CalibrationLabeledReply",
    "SemanticBaseline",
    "SemanticCalibrationSet",
    "SemanticCaseScore",
    "SemanticCriterionScore",
    "SemanticJudge",
    "SemanticJudgment",
    "SemanticJudgeRequest",
    "SemanticLabel",
    "SemanticScoreKey",
    "build_baseline",
    "calibrate_judge",
    "compare_to_baseline",
    "load_calibration_labels",
    "score_reply",
]
