"""Real shared runner/launcher paused at durable review; synthetic executor only."""

import asyncio
import json
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from cryptography.fernet import Fernet

from scripts import execute_eval_campaign as cli
from src.agent.eval_campaign import EvalCampaignPlan, EvalUsageRecorder
from src.agent.eval_campaign_runner import EvalCampaignRunner, campaign_cases_fingerprint
from src.agent.eval_diagnostics import EvalPresentationError, TerminalDiagnostic
from src.agent.eval_durable_review import DurableCampaignReviewer, case_record
from src.agent.eval_evidence import EvalEvidenceStore
from src.agent.evals import EvalObservation
from src.domain.interactions.reply import AgentReply
from src.domain.llm_access.models import LlmUsageEventCreate
from src.domain.runtime_config.models import RuntimeConfigSnapshot

ROOT = Path(__file__).resolve().parents[2]


async def test_terminal_failure_survives_encrypted_checkpoint_status_without_review_or_replay(
    tmp_path,
):
    folder = ROOT / "evals/response_style"
    plan = EvalCampaignPlan.model_validate_json((folder / "bl48-campaign-plan.json").read_text())
    snapshot = RuntimeConfigSnapshot.model_validate_json(
        (folder / "runtime-rev8-snapshot.json").read_text(),
    )
    cases = plan.validate_snapshot(snapshot)
    identity = {"code_sha": "a" * 40, "source_fingerprint": "b" * 64, "worktree": "clean"}
    key = Fernet.generate_key().decode()
    store = EvalEvidenceStore(tmp_path / "evidence", key)
    case_records = [case_record(case) for case in cases]
    run = store.create(identity, plan.model_dump(mode="json"), case_records,
                       snapshot.model_dump(mode="json", by_alias=True), synthetic_approved=True)
    calls = []
    recorder = EvalUsageRecorder()

    async def execute(request):
        calls.append(request.case.case_id)
        first = len(calls) == 1
        for _ in range(3 if first else 2):
            await recorder.record(LlmUsageEventCreate(
                interaction_id=uuid4(), llm_call_id=uuid4(), config_revision=8,
                logical_route=plan.logical_route,
                effective_gateway_route=plan.effective_gateway_route,
                status="completed", estimated_cost=0.001,
            ))
        if not first:
            raise EvalPresentationError(TerminalDiagnostic(
                reason="missing_terminal", presentation_count=0, tool_execution_count=1,
                run_status="COMPLETED",
            ))
        return EvalObservation(
            outcome="tool_call", tool_names=(request.case.required_tool,),
            requires_user_confirmation=True,
            reply=AgentReply(answer="", proposal_text="PRIVATE_SYNTHETIC_RESPONSE"),
        )

    runner = EvalCampaignRunner(
        plan=plan, snapshot=snapshot,
        executor=type("Executor", (), {"execute": staticmethod(execute)})(), recorder=recorder,
        reviewer=DurableCampaignReviewer(store, run), code_sha=identity["code_sha"],
    )
    task = asyncio.create_task(runner.run(
        checkpoint=lambda report: store.append(run, "checkpoint", report),
    ))
    try:
        for _ in range(50):
            if store.observation(run, cases[0].case_id):
                break
            await asyncio.sleep(0.02)
        assert not task.done()
        for index in range(len(cases[0].response_criteria)):
            store.review(run, cases[0].case_id, index, "pass", "owner")
        await asyncio.wait_for(task, 4)
    finally:
        if not task.done():
            task.cancel()
            await task
    reopened = EvalEvidenceStore(store.root, key)
    status = reopened.status(run)
    assert status["execution_status"] == "stopped" and status["recorded_model_calls"] == 5
    assert status["cases"][0]["execution_status"] == "passed"
    failed = status["cases"][1]
    assert failed["error_class"] == "InvalidPresentationOutputError"
    assert failed["terminal_diagnostic"]["reason"] == "missing_terminal"
    assert failed["model_calls"] == 2 and failed["usage_error_count"] == 0
    assert failed["evidence_available"] is False and failed["criteria"] == []
    assert all(item["execution_status"] == "not_started" for item in status["cases"][2:])
    assert "PRIVATE" not in json.dumps(status)
    assert all(b"PRIVATE" not in path.read_bytes() for path in (store.root / run).glob("*.enc"))
    with pytest.raises(FileExistsError):
        reopened.create(identity, plan.model_dump(mode="json"), case_records,
                        snapshot.model_dump(mode="json", by_alias=True), synthetic_approved=True)
    assert len(calls) == 2


async def test_disconnecting_reviewer_does_not_restart_model_and_failure_stops_next_case(
    tmp_path, monkeypatch,
):
    folder = ROOT / "evals/response_style"
    plan = EvalCampaignPlan.model_validate_json((folder / "bl48-campaign-plan.json").read_text())
    snapshot = RuntimeConfigSnapshot.model_validate_json(
        (folder / "runtime-rev8-snapshot.json").read_text()
    )
    cases = plan.validate_snapshot(snapshot)
    identity = {"code_sha": "a" * 40, "source_fingerprint": "b" * 64,
                "worktree": "clean", "identity_source": "sealed_image"}
    key = Fernet.generate_key().decode()
    store = EvalEvidenceStore(tmp_path / "evidence", key)
    run = store.create(identity, plan.model_dump(mode="json"), [case_record(c) for c in cases],
                       snapshot.model_dump(mode="json", by_alias=True), synthetic_approved=True)
    env = {
        "ANCORA_EVAL_APPROVED_PLAN": plan.checksum(), "ANCORA_EVAL_APPROVED_SHA": "a" * 40,
        "ANCORA_EVAL_APPROVED_SOURCE": "b" * 64,
        "ANCORA_EVAL_APPROVED_CASES": campaign_cases_fingerprint(cases),
        "ANCORA_EVAL_SYNTHETIC_APPROVED": "1", "ANCORA_EVAL_EXTERNAL_BUDGET_VERIFIED": "1",
        "ANCORA_EVAL_SNAPSHOT_PROVENANCE_ACCEPTED": "1", "ANCORA_EVAL_HUMAN_REVIEW_APPROVED": "1",
        "ANCORA_EVAL_GATEWAY_URL": "http://gateway.railway.internal:4000/v1",
        "ANCORA_EVAL_GATEWAY_KEY": "fixture-placeholder-not-real",
    }
    monkeypatch.setattr(cli, "validate_state_directory", lambda *_a, **_k: None)
    monkeypatch.setattr(cli, "source_identity", lambda: identity)
    monkeypatch.setattr(cli, "open_review_console", lambda: pytest.fail("worker must not use TTY"))
    original = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: original(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json={
            "data": [{"id": plan.effective_gateway_route}],
        })), **kwargs,
    ))
    calls = []
    def build(plan, snapshot, env, recorder, **kwargs):
        async def execute(request):
            calls.append(request.case.case_id)
            await recorder.record(LlmUsageEventCreate(
                interaction_id=uuid4(), llm_call_id=uuid4(), config_revision=8,
                logical_route=plan.logical_route,
                effective_gateway_route=plan.effective_gateway_route,
                status="completed", estimated_cost=0.001,
            ))
            return EvalObservation(
                outcome="tool_call", tool_names=(request.case.required_tool,),
                requires_user_confirmation=request.case.requires_user_confirmation,
                reply=AgentReply(answer="", proposal_text="synthetic private"),
            )
        return type("Executor", (), {"execute": staticmethod(execute)})()
    monkeypatch.setattr(cli, "build_campaign_executor", build)
    task = asyncio.create_task(cli.execute_approved(plan, snapshot, identity, env, tmp_path,
                                                   durable=(store, run)))
    for _ in range(50):
        if store.observation(run, cases[0].case_id):
            break
        await asyncio.sleep(0.02)
    assert len(calls) == 1 and not task.done()
    store.review(run, cases[0].case_id, 0, "pass", "owner")
    # The SSH/review process can disappear here; labels and observation already exist.
    reopened = EvalEvidenceStore(store.root, key)
    assert reopened.observation(run, cases[0].case_id)
    assert len(calls) == 1 and not task.done()
    store.review(run, cases[0].case_id, 1, "fail", "owner")
    report = await asyncio.wait_for(task, 4)
    assert report["status"] == "stopped" and len(calls) == 1
    assert report["results"][0]["semantic_status"] == "failed"
    assert all(item["status"] == "not_started" for item in report["results"][1:])
    assert "private" not in str(store.status(run))
    with pytest.raises(FileExistsError):
        await cli.execute_approved(plan, snapshot, identity, env, tmp_path, durable=(store, run))
    assert len(calls) == 1
