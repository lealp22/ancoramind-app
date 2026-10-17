"""Serial, one-shot eval campaign; no canonical persistence or paid auto-retries."""

from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import Awaitable, Callable
from decimal import Decimal
from typing import Literal, Protocol, TextIO

from src.agent.eval_campaign import EvalCampaignPlan, EvalUsageRecorder
from src.agent.eval_tools import SyntheticProposalStore, build_eval_tools
from src.agent.evals import (
    EvalCase,
    EvalExecutionRequest,
    EvalObservation,
    SyntheticEvalExecutor,
    evaluate_observation,
)
from src.domain.llm_access.models import LlmUsageEventCreate
from src.domain.runtime_config.models import RuntimeConfigSnapshot

ReviewLabel = Literal["pass", "fail", "not_evaluated"]


class CampaignReviewer(Protocol):
    async def review(
        self, case: EvalCase, observation: EvalObservation,
    ) -> tuple[ReviewLabel, ...]: ...


def campaign_cases_fingerprint(cases: tuple[EvalCase, ...]) -> str:
    """Bind approval to actual synthetic cases/rubric, not just case IDs."""
    content = [{
        "id": case.case_id, "input": case.input_text, "context": dict(case.synthetic_context),
        "outcome": case.expected_outcome, "required_tool": case.required_tool,
        "forbidden_tools": sorted(case.forbidden_tools),
        "requires_user_confirmation": case.requires_user_confirmation,
        "criteria": list(case.response_criteria),
    } for case in cases]
    return hashlib.sha256(
        json.dumps(content, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()


class TerminalCampaignReviewer:
    """Synthetic text to an explicitly opened human console, never report/stdout.

    This is human review of this exact run, not a calibrated automated judge or
    permission to write replies to logs/files. Closing the console aborts review.
    """

    def __init__(self, reader: TextIO, writer: TextIO) -> None:
        if not reader.isatty() or not writer.isatty():
            raise ValueError("eval_human_console_required")
        self._reader = reader
        self._writer = writer

    async def review(self, case: EvalCase, observation: EvalObservation) -> tuple[ReviewLabel, ...]:
        reply = observation.reply
        if reply is None:
            return tuple("not_evaluated" for _ in case.response_criteria)
        # JSON escaping prevents synthetic/model text from injecting terminal
        # escape sequences or impersonating the rubric's console controls.
        self._writer.write(
            "\nCaso sintético: " + case.case_id
            + "\nInput (DATA): " + json.dumps(case.input_text, ensure_ascii=True)
            + "\nContexto (DATA): " + json.dumps(dict(case.synthetic_context), ensure_ascii=True)
            + "\nanswer (DATA): " + json.dumps(reply.answer, ensure_ascii=True)
            + "\nproposal_text (DATA): " + json.dumps(reply.proposal_text, ensure_ascii=True)
            + "\nTools: " + json.dumps(observation.tool_names) + "\n"
        )
        labels: list[ReviewLabel] = []
        for index, criterion in enumerate(case.response_criteria):
            self._writer.write(
                f"Criterio {index}: " + json.dumps(criterion, ensure_ascii=True)
                + "\n[p] pass / [f] fail / [x] not_evaluated (vacío = detener): "
            )
            self._writer.flush()
            choices: dict[str, ReviewLabel] = {
                "p": "pass", "pass": "pass", "f": "fail", "fail": "fail",
                "x": "not_evaluated", "not_evaluated": "not_evaluated", "": "not_evaluated",
            }
            while True:
                raw = (await asyncio.to_thread(self._reader.readline)).strip().casefold()
                if raw in choices:
                    label = choices[raw]
                    break
                self._writer.write("Entrada no válida. Usa p / f / x (vacío = detener): ")
                self._writer.flush()
            labels.append(label)
            if label != "pass":
                labels.extend("not_evaluated" for _ in case.response_criteria[index + 1:])
                break
        return tuple(labels)


def _costs(events: list[LlmUsageEventCreate], plan: EvalCampaignPlan) -> dict[str, object]:
    if not events or len(events) > plan.budget.max_model_calls:
        raise ValueError("eval_usage_missing_or_excessive")
    for event in events:
        if (
            event.status != "completed" or event.retry_count != 0 or event.fallback_used
            or event.config_revision != plan.config_revision
            or event.logical_route != plan.logical_route
            or event.effective_gateway_route != plan.effective_gateway_route
            or event.estimated_cost is None
        ):
            raise ValueError("eval_usage_invalid")
    estimated = sum((Decimal(str(event.estimated_cost)) for event in events), Decimal(0))
    ceiling = Decimal(str(plan.budget.max_estimated_cost_usd))
    known_actual = [Decimal(str(event.actual_cost)) for event in events
                    if event.actual_cost is not None]
    if (
        any(not cost.is_finite() or cost < 0 or cost > ceiling for cost in known_actual)
        or sum(known_actual, Decimal(0)) > ceiling
    ):
        raise ValueError("eval_case_cost_exceeded")
    actual = (
        sum((Decimal(str(event.actual_cost)) for event in events), Decimal(0))
        if all(event.actual_cost is not None for event in events) else None
    )
    if (
        not estimated.is_finite() or estimated < 0 or estimated > ceiling
        or (actual is not None and (not actual.is_finite() or actual < 0 or actual > ceiling))
    ):
        raise ValueError("eval_case_cost_exceeded")
    return {
        "model_calls": len(events), "estimated_cost_usd": str(estimated),
        "actual_cost_usd": str(actual) if actual is not None else None,
        "usage": [{
            "llm_call_id": str(event.llm_call_id), "correlation_id": str(event.interaction_id),
            "input_tokens": event.input_tokens, "output_tokens": event.output_tokens,
            "estimated_cost_usd": event.estimated_cost, "actual_cost_usd": event.actual_cost,
            "status": event.status, "retry_count": event.retry_count,
        } for event in events],
    }


class EvalCampaignRunner:
    """All cases reserved up-front, serial, single-use; failure stops later work."""

    def __init__(
        self, *, plan: EvalCampaignPlan, snapshot: RuntimeConfigSnapshot,
        executor: SyntheticEvalExecutor, recorder: EvalUsageRecorder,
        reviewer: CampaignReviewer, code_sha: str,
    ) -> None:
        self._plan = plan
        self._cases = plan.validate_snapshot(snapshot)
        self._executor = executor
        self._recorder = recorder
        self._reviewer = reviewer
        self._used = False
        self._tool_names = {tool.__name__ for tool in build_eval_tools(SyntheticProposalStore())}
        reserve = Decimal(str(plan.budget.max_estimated_cost_usd)) * len(self._cases)
        # Revalidated before any callback/model work, no release/reuse on failure.
        if reserve > plan.total_estimated_cost_usd:
            raise ValueError("eval_campaign_total_reserve_insufficient")
        self.report: dict[str, object] = {
            **plan.metadata(), "code_sha": code_sha,
            "cases_fingerprint": campaign_cases_fingerprint(self._cases),
            "reserved_estimated_cost_usd": str(reserve), "inference_started": False,
            "status": "reserved", "review_method": "human_console_v1",
            "results": [{"case_id": case.case_id, "status": "not_started"} for case in self._cases],
        }

    async def run(
        self, *, checkpoint: Callable[[dict[str, object]], None] | None = None,
        before_case: Callable[[], Awaitable[None]] | None = None,
    ) -> dict[str, object]:
        if self._used:
            raise ValueError("eval_campaign_already_consumed")
        self._used = True
        results: list[dict[str, object]] = []
        self.report["results"] = results
        self.report["status"] = "running"
        try:
            for index, case in enumerate(self._cases):
                result: dict[str, object] = {"case_id": case.case_id, "status": "started"}
                results.append(result)
                if checkpoint:
                    checkpoint(self.report)
                try:
                    if before_case:
                        await before_case()
                    self.report["inference_started"] = True
                    if checkpoint:
                        checkpoint(self.report)  # durable intent before crossing the model boundary
                    offset = len(self._recorder.events)
                    request = EvalExecutionRequest(case, self._plan.logical_route,
                                                   self._plan.config_revision)
                    observation = await self._executor.execute(request)
                    result.update(_costs(self._recorder.events[offset:], self._plan))
                    if any(name not in self._tool_names for name in observation.tool_names):
                        raise ValueError("eval_observed_unknown_tool")
                    result["observed_tool_names"] = list(observation.tool_names)
                    verdict = evaluate_observation(request, observation)
                    result["deterministic_status"] = "passed" if verdict.passed else "failed"
                    if not verdict.passed:
                        raise ValueError("eval_deterministic_failed")
                    labels = await self._reviewer.review(case, observation)
                    if len(labels) != len(case.response_criteria) or not labels:
                        raise ValueError("eval_review_incomplete")
                    if any(label not in {"pass", "fail", "not_evaluated"} for label in labels):
                        raise ValueError("eval_review_invalid")
                    result["criteria"] = [
                        {"index": i, "label": label} for i, label in enumerate(labels)
                    ]
                    result["semantic_status"] = (
                        "failed" if "fail" in labels
                        else "not_evaluated" if "not_evaluated" in labels else "passed"
                    )
                    if result["semantic_status"] != "passed":
                        raise ValueError("eval_review_not_passed")
                    result["status"] = "passed"
                except (Exception, asyncio.CancelledError) as error:
                    # No exception/response/provider text is safe report material.
                    result["status"] = "stopped"
                    result.setdefault("semantic_status", "not_evaluated")
                    result["error_class"] = type(error).__name__
                    results.extend({"case_id": c.case_id, "status": "not_started"}
                                   for c in self._cases[index + 1:])
                    self.report["status"] = "stopped"
                    return self.report
                if checkpoint:
                    checkpoint(self.report)
            self.report["status"] = "passed"
            self.report["semantic_status"] = "passed"
            return self.report
        finally:
            # Safe even on cancellation: completed replies are not in the report.
            self.report["recorded_model_calls"] = len(self._recorder.events)
            self.report["usage"] = self._recorder.metadata()
            if checkpoint:
                checkpoint(self.report)
