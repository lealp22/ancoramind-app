"""Isolated execution harness for synthetic governed-agent evaluations.

The harness owns catalog materialization and deterministic expectation checks. It
does not create an Agent, provider, LLMAccess instance, database session, or
production tool. Callers must inject an executor that uses only synthetic
fixtures and simulated tools. Inputs and responses remain in memory; persisted
or emitted reports use :meth:`EvalCaseResult.metadata` only.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from scripts.run_evals import EVALS_DIR, CatalogValidationError, load_catalog, validate_catalogs


@dataclass(frozen=True)
class EvalCase:
    """One validated synthetic case materialized for an isolated executor.

    ``synthetic_context`` is untrusted test data. It must never establish the
    executor's identity, permissions, or confirmation state.
    """

    case_id: str
    category: str
    input_text: str
    synthetic_context: Mapping[str, object]
    expected_outcome: str
    required_tool: str | None
    forbidden_tools: frozenset[str]
    requires_user_confirmation: bool
    response_criteria: tuple[str, ...]


@dataclass(frozen=True)
class EvalExecutionRequest:
    """In-memory request passed to an explicitly injected isolated executor."""

    case: EvalCase
    logical_route: str
    config_revision: int


@dataclass(frozen=True)
class EvalObservation:
    """Observable result from an isolated run; response text is never reported."""

    outcome: str
    tool_names: tuple[str, ...] = ()
    requires_user_confirmation: bool = False
    response_text: str | None = None


class SyntheticEvalExecutor(Protocol):
    """Port for one isolated run with synthetic context and simulated tools only."""

    async def execute(self, request: EvalExecutionRequest) -> EvalObservation: ...


@dataclass(frozen=True)
class EvalCaseResult:
    """Deterministic verdict for one execution; sensitive values stay in memory."""

    case_id: str
    category: str
    logical_route: str
    config_revision: int
    expected_outcome: str
    observed_outcome: str
    expected_required_tool: str | None
    observed_tool_names: tuple[str, ...]
    expected_requires_user_confirmation: bool
    observed_requires_user_confirmation: bool
    passed: bool
    failures: tuple[str, ...]
    response_text: str | None = None

    def metadata(self) -> dict[str, object]:
        """Return the safe report projection, deliberately excluding input/context/response."""

        return {
            "case_id": self.case_id,
            "category": self.category,
            "logical_route": self.logical_route,
            "config_revision": self.config_revision,
            "expected_outcome": self.expected_outcome,
            "observed_outcome": self.observed_outcome,
            "expected_required_tool": self.expected_required_tool,
            "observed_tool_names": list(self.observed_tool_names),
            "expected_requires_user_confirmation": self.expected_requires_user_confirmation,
            "observed_requires_user_confirmation": self.observed_requires_user_confirmation,
            "passed": self.passed,
            "failures": list(self.failures),
        }


def load_eval_cases(
    *,
    categories: set[str] | None = None,
    evals_dir: Path = EVALS_DIR,
) -> list[EvalCase]:
    """Validate selected catalogs and materialize only their synthetic cases."""

    summaries = validate_catalogs(evals_dir=evals_dir, categories=categories)
    cases: list[EvalCase] = []
    for summary in summaries:
        catalog = load_catalog(summary.path)
        for raw_case in catalog["cases"]:
            expected = raw_case["expected"]
            cases.append(
                EvalCase(
                    case_id=raw_case["id"],
                    category=summary.category,
                    input_text=raw_case["input"],
                    synthetic_context=dict(raw_case.get("context", {})),
                    expected_outcome=expected["outcome"],
                    required_tool=expected.get("required_tool"),
                    forbidden_tools=frozenset(expected.get("forbidden_tools", [])),
                    requires_user_confirmation=expected["requires_user_confirmation"],
                    response_criteria=tuple(expected.get("response_criteria", [])),
                )
            )
    return cases


def evaluate_observation(
    request: EvalExecutionRequest,
    observation: EvalObservation,
) -> EvalCaseResult:
    """Compare a run observation with non-negotiable deterministic expectations."""

    case = request.case
    observed_tools = tuple(observation.tool_names)
    failures: list[str] = []
    if observation.outcome != case.expected_outcome:
        failures.append(
            f"outcome expected {case.expected_outcome!r}, observed {observation.outcome!r}"
        )
    if case.required_tool is not None and case.required_tool not in observed_tools:
        failures.append(f"required tool not observed: {case.required_tool}")

    forbidden_observed = sorted(case.forbidden_tools.intersection(observed_tools))
    if forbidden_observed:
        failures.append(f"forbidden tools observed: {', '.join(forbidden_observed)}")
    if observation.requires_user_confirmation != case.requires_user_confirmation:
        failures.append(
            "user confirmation expected "
            f"{case.requires_user_confirmation!r}, observed "
            f"{observation.requires_user_confirmation!r}"
        )

    return EvalCaseResult(
        case_id=case.case_id,
        category=case.category,
        logical_route=request.logical_route,
        config_revision=request.config_revision,
        expected_outcome=case.expected_outcome,
        observed_outcome=observation.outcome,
        expected_required_tool=case.required_tool,
        observed_tool_names=observed_tools,
        expected_requires_user_confirmation=case.requires_user_confirmation,
        observed_requires_user_confirmation=observation.requires_user_confirmation,
        passed=not failures,
        failures=tuple(failures),
        response_text=observation.response_text,
    )


async def execute_cases(
    cases: Iterable[EvalCase],
    *,
    executor: SyntheticEvalExecutor,
    logical_route: str,
    config_revision: int,
) -> list[EvalCaseResult]:
    """Execute synthetic cases serially and return in-memory deterministic verdicts."""

    if not logical_route.strip():
        raise ValueError("logical_route must be a non-empty string")
    if config_revision < 0:
        raise ValueError("config_revision must be non-negative")

    results: list[EvalCaseResult] = []
    for case in cases:
        request = EvalExecutionRequest(
            case=case,
            logical_route=logical_route,
            config_revision=config_revision,
        )
        observation = await executor.execute(request)
        results.append(evaluate_observation(request, observation))
    return results


def metadata_report(results: Sequence[EvalCaseResult]) -> dict[str, object]:
    """Build a content-free summary suitable for a future durable report or CI artifact."""

    return {
        "case_count": len(results),
        "passed_count": sum(result.passed for result in results),
        "failed_count": sum(not result.passed for result in results),
        "results": [result.metadata() for result in results],
    }


__all__ = [
    "CatalogValidationError",
    "EvalCase",
    "EvalCaseResult",
    "EvalExecutionRequest",
    "EvalObservation",
    "SyntheticEvalExecutor",
    "evaluate_observation",
    "execute_cases",
    "load_eval_cases",
    "metadata_report",
]
