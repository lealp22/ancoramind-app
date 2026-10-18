"""Physical BL-8 eval executor: a real governed Agent against simulated tools.

specs/018 T6. ``src/agent/evals.py`` already validates catalogs and compares a
deterministic :class:`~src.agent.evals.EvalObservation` against each case's
expectations; until now every injected executor was a test double. This
module provides the real one: it builds one governed-shaped ``Agent`` per
case — model resolved through an injected :class:`LLMAccess` (never a direct
provider), its own isolated :class:`ExecutionContext`/budget/config snapshot,
and the simulated tool catalog from :mod:`src.agent.eval_tools` (never
production tools) — runs it, and derives the observation from facts the code
can observe directly on the run output.

Deliberately **not** reused from the production composition
(:class:`src.agent.governed_agent_factory.GovernedAgentFactory`): that
factory hardcodes ``add_history_to_context=True`` and a real ``db`` session,
both tied to persisting a multi-turn Telegram conversation. An eval case is a
single synthetic turn with no session to persist, so this module builds its
own minimal ``Agent`` instead, preserving the same governance invariants
(model via ``LLMAccess``, ``tool_call_limit`` from the run's budget,
``retries=0``, ``telemetry=False``, the same budget tool hook).

**Scope boundary (T6 vs T7/T8), by design:**

- No credentials, Gateway call, or real provider is ever constructed here;
  the injected ``llm_access`` is the caller's responsibility, and wiring a
  real ``AgnoLLMAccess`` to actually spend budget is T7 — explicitly gated on
  separate credential/cost approval, not part of this module.
- ``outcome`` is derived **only from code-observable facts** (which tools
  were called): a tool observed → ``"tool_call"``; no tool observed →
  ``"no_tool_call"``. This last value is a deliberate sentinel, distinct from
  the catalog's ``"clarify"``/``"safe_response"`` labels: telling those two
  apart requires judging the free-text response semantically (is this a
  question, or a declarative safe answer?), which this harness does not do.
  That is explicitly T8 (an optional semantic judge such as Jev) — a case
  expecting ``"clarify"`` or ``"safe_response"`` will not match on outcome
  here, which is a known, documented gap, not a bug.
- ``requires_user_confirmation`` is derived the same way: ``True`` iff any
  observed tool name starts with ``"propose_"``.

**Simulating ``synthetic_context`` without granting authority from it:**
``EvalCase.synthetic_context`` is untrusted test data (see its docstring in
``src/agent/evals.py``) and must never *itself* establish confirmation state.
Legacy confirmation cases require a separate Core consent harness and are
rejected before resolving any model. This executor cannot certify them.
For other cases this executor seeds the *code-side* ``SyntheticProposalStore``
(ground truth owned by the harness) and separately lets the model see a pending
proposal as synthetic conversation history. It grants no execution authority.
The model can only read and propose: all ``execute_*`` adapters are excluded
from its catalog, just like production (BL-39/40, 2026-10-11).
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
from collections.abc import Mapping
from typing import Any
from uuid import uuid4

from agno.agent import Agent
from agno.media import File
from agno.models.message import Message
from agno.run import RunContext
from agno.run.agent import RunOutput

from src.agent.eval_tools import SyntheticProposalStore, build_eval_tools
from src.agent.evals import EvalExecutionRequest, EvalObservation
from src.agent.instructions import assemble_instructions
from src.agent.reply_presentation import (
    build_reply_presentation_tool,
    domain_tool_executions,
    reply_from_run,
)
from src.agent.tool_budget_hooks import build_budget_tool_hook
from src.agent.tool_catalog import proposal_only_tools
from src.domain.llm_access.access import LLMAccess
from src.domain.llm_access.context import execution_context_scope
from src.domain.llm_access.models import ExecutionBudget, ExecutionContext, generate_traceparent
from src.domain.runtime_config.models import (
    ExecutionBudgetConfig,
    RuntimeConfigSnapshot,
    bootstrap_runtime_configuration,
    config_checksum,
)

_EVAL_FINGERPRINT_KEY = "ancoramind-evals-synthetic-fingerprint"


def eval_snapshot_fingerprint(snapshot: RuntimeConfigSnapshot) -> str:
    """Bind an eval approval to exact typed content without rewriting legacy hashes.

    Runtime capabilities are sets; their serialization order is not stable across
    Python processes. The recorded runtime checksum remains a provenance reference,
    NOT an assertion that this eval fingerprint verifies its historical algorithm.
    """
    raw = snapshot.model_dump(mode="json", by_alias=True)
    for route in raw["config"]["routing"]["routes"].values():
        route["capabilities"] = sorted(route["capabilities"])
    return hashlib.sha256(
        json.dumps(raw, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


#: Pending-proposal kind labels seen in evals/confirmation/cases.json today,
#: mapped to a human-readable Spanish description for the synthetic prior
#: turn. An unrecognized label still works (generic fallback), so a new
#: catalog case does not require a code change here.
_PENDING_PROPOSAL_LABELS: Mapping[str, str] = {
    "create_vehicle": "🚗 **Propuesta de registro de vehículo**",
    "register_vehicle": "🚗 **Propuesta de registro de vehículo**",
    "create_reminder": "⏰ **Propuesta de recordatorio**",
    "create_calendar_event": "📅 **Propuesta de evento**",
    "register_vehicle_maintenance": "🔧 **Propuesta de mantenimiento**",
    "remember_note": "📝 **Propuesta de nota**",
}


def _pending_proposal_message(proposal_id: str, kind_label: str) -> Message:
    label = _PENDING_PROPOSAL_LABELS.get(kind_label, "📋 **Propuesta pendiente**")
    return Message(
        role="assistant",
        content=f"{label} (`{proposal_id}`)\n\n¿Confirmas que la ejecute?",
    )


class GovernedPhysicalEvalExecutor:
    """Runs a real governed Agent, with simulated tools, for one eval case."""

    def __init__(
        self,
        *,
        llm_access: LLMAccess,
        snapshot: RuntimeConfigSnapshot | None = None,
        budget: ExecutionBudgetConfig | None = None,
        snapshot_fingerprint: str | None = None,
    ) -> None:
        self._llm_access = llm_access
        if snapshot is None:
            config = bootstrap_runtime_configuration()
            snapshot = RuntimeConfigSnapshot(
                revision=0, checksum=config_checksum(config), source="bootstrap", config=config
            )
        if snapshot_fingerprint is not None and (
            snapshot_fingerprint != eval_snapshot_fingerprint(snapshot)
        ):
            raise ValueError("eval_snapshot_fingerprint_mismatch")
        self._snapshot = snapshot
        self._budget = budget or snapshot.config.execution_budget
        for name, limit in self._budget.model_dump().items():
            ceiling = getattr(snapshot.config.execution_budget, name)
            if ceiling is not None and (limit is None or limit > ceiling):
                raise ValueError("eval_budget_may_not_expand_snapshot")

    async def execute(self, request: EvalExecutionRequest) -> EvalObservation:
        if request.config_revision != self._snapshot.revision:
            raise ValueError("eval_request_revision_mismatch")
        route = self._snapshot.config.routing.routes.get(request.logical_route)
        if route is None or not {"text", "tool_calling"} <= route.capabilities:
            raise ValueError("eval_text_tool_route_required")
        case = request.case
        if case.expected_outcome == "confirm_pending_action" or (
            case.required_tool is not None and case.required_tool.startswith("execute_")
        ):
            raise ValueError("Core consent cases require a deterministic consent harness")
        fixtures = case.synthetic_context
        store = SyntheticProposalStore()

        run_input: str | list[Message] = case.input_text
        pending = fixtures.get("pending_proposal")
        if isinstance(pending, Mapping):
            proposal_id = str(pending.get("id", ""))
            kind_label = str(pending.get("tool_name", ""))
            if proposal_id:
                store.seed(proposal_id, kind_label)
                run_input = [
                    _pending_proposal_message(proposal_id, kind_label),
                    Message(role="user", content=case.input_text),
                ]

        files: list[File] | None = None
        attachment = fixtures.get("attachment")
        if isinstance(attachment, str) and attachment and "analysis_completed" not in fixtures:
            files = [
                File(
                    content=b"synthetic-eval-fixture-no-real-bytes",
                    filename=attachment,
                    mime_type="application/octet-stream",
                )
            ]

        tools = build_eval_tools(store, context_fixtures=fixtures)
        context = self._build_execution_context()
        agent = self._build_agent(context, tools, request.logical_route)
        run_context = RunContext(
            run_id=f"eval-{case.case_id}",
            session_id=f"eval:{case.case_id}",
            user_id="eval-synthetic-user",
        )

        with execution_context_scope(context):
            output: RunOutput = await asyncio.wait_for(
                agent.arun(
                    run_input,
                    stream=False,
                    user_id=run_context.user_id,
                    session_id=run_context.session_id,
                    run_id=run_context.run_id,
                    run_context=run_context,
                    files=files,
                ),
                timeout=context.budget.seconds_remaining(),
            )

        tool_names = tuple(
            name for execution in domain_tool_executions(output) if (name := execution.tool_name)
        )
        reply = reply_from_run(output)
        outcome = "tool_call" if tool_names else "no_tool_call"

        proposals = store.evidence()
        blocks = [str(p["core_block"]) for p in proposals if p["created_this_run"]]
        delivered = "\n\n".join(part for part in [reply.answer.strip(), *blocks] if part)
        trace = tuple({
            "name": execution.tool_name, "arguments": execution.tool_args,
            "result": execution.result, "error": bool(execution.tool_call_error),
        } for execution in domain_tool_executions(output))
        return EvalObservation(
            outcome=outcome,
            tool_names=tool_names,
            requires_user_confirmation=bool(blocks),
            response_text=reply.text(),
            reply=reply,
            proposals=proposals, tool_trace=trace, delivered_text=delivered,
        )

    def _build_execution_context(self) -> ExecutionContext:
        return ExecutionContext(
            correlation_id=uuid4(),
            telegram_update_id=0,
            agno_run_id=str(uuid4()),
            agno_session_id="eval-session",
            config=self._snapshot,
            budget=ExecutionBudget.from_config(
                self._budget,
                started_at_monotonic=time.monotonic(),
            ),
            traceparent=generate_traceparent(),
        )

    def _build_agent(
        self, context: ExecutionContext, tools: list[Any], logical_route: str
    ) -> Agent:
        model = self._llm_access.model_for(logical_route, context)
        model.max_tokens = self._budget.max_output_tokens
        return Agent(
            id="ancoramind-eval",
            name="AncoraMind (eval)",
            model=model,
            tools=[*proposal_only_tools(tools), build_reply_presentation_tool()],
            tool_choice="required",
            tool_call_limit=self._budget.max_tool_calls,
            retries=0,
            telemetry=False,
            tool_hooks=[build_budget_tool_hook(_EVAL_FINGERPRINT_KEY)],
            instructions=assemble_instructions(),
            add_history_to_context=False,
            add_datetime_to_context=True,
            markdown=True,
        )


__all__ = ["GovernedPhysicalEvalExecutor"]
