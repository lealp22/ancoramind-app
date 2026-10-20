"""Shared reviewer: persist evidence first, await labels independently of SSH."""

from __future__ import annotations

import asyncio
import time
from typing import Any, TextIO

from src.agent.eval_campaign_runner import ReviewLabel, TerminalCampaignReviewer
from src.agent.eval_evidence import EvalEvidenceStore
from src.agent.evals import EvalCase, EvalObservation
from src.domain.interactions.reply import AgentReply


def case_record(case: EvalCase) -> dict[str, Any]:
    return {
        "id": case.case_id, "category": case.category, "input": case.input_text,
        "context": dict(case.synthetic_context), "criteria": list(case.response_criteria),
        "expected_outcome": case.expected_outcome, "required_tool": case.required_tool,
        "forbidden_tools": sorted(case.forbidden_tools),
        "requires_user_confirmation": case.requires_user_confirmation,
    }


def stored_case(data: dict[str, Any]) -> EvalCase:
    return EvalCase(
        case_id=data["id"], category=data["category"], input_text=data["input"],
        synthetic_context=data["context"], response_criteria=tuple(data["criteria"]),
        expected_outcome=data["expected_outcome"], required_tool=data["required_tool"],
        forbidden_tools=frozenset(data["forbidden_tools"]),
        requires_user_confirmation=data["requires_user_confirmation"],
    )


def stored_observation(data: dict[str, Any]) -> EvalObservation:
    return EvalObservation(
        outcome=data["outcome"], tool_names=tuple(data["tool_names"]),
        requires_user_confirmation=data["requires_user_confirmation"],
        reply=AgentReply.model_validate(data["reply"]) if data["reply"] else None,
        proposals=tuple(data["proposals"]) if data["proposals"] is not None else None,
        tool_trace=tuple(data["tool_trace"]), delivered_text=data["delivered_text"],
    )


class DurableCampaignReviewer:
    def __init__(self, store: EvalEvidenceStore, run_id: str, *, wait_seconds: float = 7200):
        self.store = store
        self.run_id = run_id
        self.wait_seconds = wait_seconds

    def capture(self, case: EvalCase, observation: EvalObservation,
                verdict: dict[str, object]) -> None:
        self.store.capture(self.run_id, case.case_id, {
            "outcome": observation.outcome, "tool_names": list(observation.tool_names),
            "requires_user_confirmation": observation.requires_user_confirmation,
            "reply": observation.reply.model_dump() if observation.reply else None,
            "proposals": observation.proposals, "tool_trace": observation.tool_trace,
            "delivered_text": observation.delivered_text, "verdict": verdict,
        })

    async def review(self, case: EvalCase, observation: EvalObservation) -> tuple[ReviewLabel, ...]:
        # Deadline applies to waiting, not inference budget; reconnect never calls execute.
        started = time.monotonic()
        while time.monotonic() - started < self.wait_seconds:
            labels = self.store.labels(self.run_id, case.case_id)
            rejected = next((e["data"] for e in self.store.events(self.run_id)
                             if e["kind"] == "review" and e["data"]["case_id"] == case.case_id
                             and e["data"]["label"] != "pass"), None)
            if rejected:
                # Corrections remain useful for goldens; never restore inference permission.
                self.store.append(self.run_id, "review_decision", {
                    "case_id": case.case_id, "status": "stopped",
                })
                return tuple(rejected["label"] if i == rejected["index"] else
                             labels.get(i, {"label": "not_evaluated"})["label"]
                             for i in range(len(case.response_criteria)))
            if any(item["label"] != "pass" for item in labels.values()):
                return tuple(labels.get(i, {"label": "not_evaluated"})["label"]
                             for i in range(len(case.response_criteria)))
            if len(labels) == len(case.response_criteria):
                self.store.append(self.run_id, "review_decision", {
                    "case_id": case.case_id, "status": "passed",
                })
                return tuple(labels[i]["label"] for i in range(len(case.response_criteria)))
            await asyncio.sleep(1)
        raise TimeoutError("eval_review_wait_expired")


async def review_saved(store: EvalEvidenceStore, run_id: str, reviewer: str,
                       reader: TextIO, writer: TextIO) -> dict[str, Any]:
    """No provider/factory/executor. Review only observations already committed."""
    for data in store.manifest(run_id)["cases"]:
        case = stored_case(data)
        evidence = store.observation(run_id, case.case_id)
        if evidence is None:
            continue
        prior = store.labels(run_id, case.case_id)
        pending = tuple(i for i in range(len(case.response_criteria)) if i not in prior)
        if not pending:
            continue

        def save(index: int, label: ReviewLabel, *, case_id: str = case.case_id) -> None:
            store.review(run_id, case_id, index, label, reviewer)

        # One reviewer per case: the case block is printed once, then the pending
        # criteria follow (specs/045). Labels are still saved one criterion at a time.
        terminal = TerminalCampaignReviewer(reader, writer, save=save,
                                            criterion_indices=pending, pause_on_disconnect=True)
        labels = await terminal.review(case, stored_observation(evidence))
        if any(label != "pass" for label in labels):
            return store.status(run_id)
    return store.status(run_id)
