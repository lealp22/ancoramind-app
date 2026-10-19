"""Cumulative allowance, private persistence and request guards; no real inference."""

import asyncio
import json
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from cryptography.fernet import Fernet

from scripts import eval_console as cli
from scripts import execute_eval_campaign as launch
from src.agent.eval_campaign import EvalCampaignPlan
from src.agent.eval_campaign_runner import campaign_cases_fingerprint
from src.agent.eval_durable_review import case_record
from src.agent.eval_evidence import EvalEvidenceStore
from src.agent.eval_validation_session import (
    EvalSessionError,
    EvalValidationSession,
    session_scope,
)
from src.agent.evals import EvalObservation
from src.domain.interactions.reply import AgentReply
from src.domain.llm_access.context import execution_context_scope
from src.domain.llm_access.models import ExecutionBudget, ExecutionContext, LlmUsageEventCreate
from src.domain.runtime_config.models import RuntimeConfigSnapshot

ROOT = Path(__file__).resolve().parents[2]
SOURCE = "b" * 64
KEY = "synthetic-not-a-real-key"


@pytest.fixture
def configured(tmp_path, monkeypatch):
    folder = ROOT / "evals/response_style"
    plan = EvalCampaignPlan.model_validate_json((folder / "bl48-campaign-plan.json").read_text())
    snapshot = RuntimeConfigSnapshot.model_validate_json(
        (folder / "runtime-rev8-snapshot.json").read_text(),
    )
    store = EvalEvidenceStore(tmp_path / "evidence", Fernet.generate_key().decode())
    session = EvalValidationSession(store)
    session.initialize(scope=session_scope(ROOT, plan, snapshot), plan=plan, key=KEY, history=[])
    monkeypatch.setenv("ANCORA_EVAL_STATE_DIR", str(tmp_path))
    monkeypatch.setenv("ANCORA_EVAL_GATEWAY_KEY", KEY)
    monkeypatch.setenv("ANCORA_EVAL_GATEWAY_URL", "http://gateway.railway.internal:4000/v1")
    monkeypatch.setattr(cli, "validate_state_directory", lambda *_a, **_k: None)
    monkeypatch.setattr(launch, "validate_state_directory", lambda *_a, **_k: None)
    identity = {"code_sha": "a" * 40, "source_fingerprint": SOURCE,
                "worktree": "clean", "identity_source": "sealed_image"}
    monkeypatch.setattr(cli, "source_identity", lambda: identity)
    monkeypatch.setattr(launch, "source_identity", lambda: identity)
    return session, store, plan, snapshot, tmp_path, identity


def info(**changes):
    return {
        "expires": (datetime.now(UTC) + timedelta(days=7)).isoformat(),
        "models": ["ancoramind-default-r4"], "spend": 0.004, "max_budget": 0.10,
        "key_alias": "ancoramind-evals-reusable", "max_parallel_requests": 1,
        "allowed_routes": ["/v1/models", "/key/info", "/v1/chat/completions"], **changes,
    }


def event(plan, **changes):
    return LlmUsageEventCreate(**{
        "interaction_id": uuid4(), "llm_call_id": uuid4(), "config_revision": 8,
        "logical_route": plan.logical_route,
        "effective_gateway_route": plan.effective_gateway_route,
        "status": "completed", "estimated_cost": 0.001, "actual_cost": 0.001, **changes,
    })


def test_import_keeps_unknown_cost_and_identity_does_not_reset_allowance(configured):
    _, store, plan, snapshot, _, _ = configured
    # Separate synthetic volume to model initial import, never reset a real ledger.
    other = EvalEvidenceStore(store.root.parent / "imported", Fernet.generate_key().decode())
    session = EvalValidationSession(other)
    results = [{"case_id": case, "status": "not_started"} for case in plan.case_ids]
    results[0].update(status="passed")
    results[1].update(status="stopped", error_class="InvalidPresentationOutputError")
    history = [{"run_id": "c" * 32, "source": SOURCE, "results": results,
                "usage_complete": True}]
    report = session.initialize(scope=session_scope(ROOT, plan, snapshot), plan=plan,
                                key=KEY, history=history)
    assert report["charged_or_reserved_usd"] == "0.04"
    assert report["available_usd"] == "0.06"
    assert [item["status"] for item in report["attempts"]] == ["passed", "failed"]
    first = session.path.read_bytes()
    session.initialize(scope=session_scope(ROOT, plan, snapshot), plan=plan, key=KEY, history=[])
    assert session.path.read_bytes() == first
    assert KEY.encode() not in first and b"response_style" not in first
    assert KEY not in json.dumps(session.summary())
    session.observe_gateway(info(spend=0.05), KEY, plan)
    assert session.remaining() == Decimal("0.05")
    with pytest.raises(EvalSessionError, match="decreased"):
        session.observe_gateway(info(spend=0.01), KEY, plan)


@pytest.mark.parametrize("change", [
    {"spend": -1}, {"spend": float("nan")}, {"max_budget": 0.20},
    {"max_budget": None}, {"budget_duration": "1d"}, {"budget_reset_at": "later"},
    {"models": ["other"]}, {"blocked": True}, {"auto_rotate": True},
    {"max_parallel_requests": 2}, {"max_parallel_requests": True},
    {"allowed_routes": ["llm_api_routes"]},
    {"expires": (datetime.now(UTC) - timedelta(days=1)).isoformat()},
    {"permissions": {"admin": True}},
])
def test_gateway_drift_blocks_without_changing_ledger(configured, change):
    session, _, plan, *_ = configured
    original = session.path.read_bytes()
    with pytest.raises((ValueError, TypeError)):
        session.observe_gateway(info(**change), KEY, plan)
    assert session.path.read_bytes() == original


def test_case_reservation_is_atomic_persistent_and_uncertain_is_not_free(configured):
    session, store, plan, *_ = configured
    case = plan.case_ids[1]
    with pytest.raises(EvalSessionError, match="unverified"):
        session.reserve("c" * 32, case, SOURCE, Decimal("0.02"))
    session.observe_gateway(info(), KEY, plan)
    session.reserve("c" * 32, case, SOURCE, Decimal("0.02"))
    reopened = EvalValidationSession(store)
    with pytest.raises(EvalSessionError, match="consumed_or_uncertain"):
        reopened.reserve("d" * 32, case, "e" * 64, Decimal("0.02"))
    session.settle([event(plan, status="error", actual_cost=None)], passed=False)
    assert session.summary()["charged_or_reserved_usd"] == "0.024"
    assert session.summary()["attempts"][0]["status"] == "uncertain"
    with pytest.raises(EvalSessionError, match="consumed_or_uncertain"):
        reopened.reserve("d" * 32, case, "e" * 64, Decimal("0.02"))


def test_completed_invalid_presentation_can_be_diagnosed_on_new_candidate_only(configured):
    session, _, plan, *_ = configured
    session.observe_gateway(info(), KEY, plan)
    case = plan.case_ids[1]
    session.reserve("c" * 32, case, SOURCE, Decimal("0.02"))
    session.settle([event(plan)], passed=False)
    assert session.summary()["attempts"][0]["charged"] == "0.02"
    assert session.summary()["attempts"][0]["status"] == "failed"
    with pytest.raises(EvalSessionError, match="consumed"):
        session.reserve("d" * 32, case, SOURCE, Decimal("0.02"))
    session.reserve("d" * 32, case, "e" * 64, Decimal("0.02"))
    assert session.summary()["charged_or_reserved_usd"] == "0.044"


def test_exact_remaining_amount_stops_before_case_not_after_spend(configured):
    session, _, plan, *_ = configured
    session.observe_gateway(info(spend=0.09), KEY, plan)
    with pytest.raises(EvalSessionError, match="insufficient"):
        session.reserve("c" * 32, plan.case_ids[0], SOURCE, Decimal("0.02"))
    assert session.summary()["attempts"] == []
    session.reserve("c" * 32, plan.case_ids[0], SOURCE, Decimal("0.01"))
    assert session.remaining() == 0


def test_single_worker_lease_and_crash_marker_never_auto_removed(configured):
    session, store, _, _, _, identity = configured
    with session.worker("c" * 32, identity):
        with (pytest.raises(FileExistsError),
              EvalValidationSession(store).worker("d" * 32, identity)):
            pytest.fail("two workers")
        assert (session.folder / "worker.lease").exists()
    assert not (session.folder / "worker.lease").exists()
    (session.folder / "worker.lease").write_text("dead-worker")
    with pytest.raises(FileExistsError), session.worker("e" * 32, identity):
        pytest.fail("lease cleared without inspection")


def test_scope_accepts_diagnostics_not_behavior_changes(tmp_path, configured):
    _, _, plan, snapshot, *_ = configured
    for name in ("src/agent/eval_tools.py", "src/agent/eval_diagnostics.py", "prompts/identity.md",
                 "evals/response_style/cases.json", "scripts/eval_console.py", "pyproject.toml",
                 "evals/Dockerfile", "evals/Dockerfile.dockerignore"):
        path = tmp_path / "scope" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("synthetic")
    root = tmp_path / "scope"
    original = session_scope(root, plan, snapshot)
    (root / "src/agent/eval_diagnostics.py").write_text("diagnostic change")
    (root / "scripts/eval_console.py").write_text("console change")
    assert session_scope(root, plan, snapshot) == original
    for name in ("src/agent/eval_tools.py", "prompts/identity.md",
                 "evals/response_style/cases.json"):
        path = root / name
        path.write_text("behavior changed")
        assert session_scope(root, plan, snapshot) != original
        path.write_text("synthetic")


def test_prepare_uses_one_session_not_stale_approval_per_sha(configured):
    session, store, plan, _, state, identity = configured
    session.observe_gateway(info(), KEY, plan)
    run = cli.prepare_session(store, state, [plan.case_ids[1]])
    decision = next(e["data"] for e in store.events(run) if e["kind"] == "approval")
    assert decision["validation_session"] is True
    assert decision["gates"]["ANCORA_EVAL_APPROVED_SHA"] == identity["code_sha"]
    assert store.manifest(run)["plan"]["case_ids"] == [plan.case_ids[1]]
    with pytest.raises(FileExistsError):
        cli.prepare_session(store, state, [plan.case_ids[1]])
    with pytest.raises(FileExistsError):
        cli.prepare_session(store, state, [plan.case_ids[2]])
    assert session.summary()["attempts"] == []  # preparation never spends or reserves calls


def test_init_without_explicit_acceptance_never_creates_allowance(configured, monkeypatch, capsys):
    _, store, *_ = configured
    monkeypatch.setattr(cli, "store_from_env", lambda _: (store, store.root.parent))
    assert cli.main(["session-init"]) == 1
    assert "session_initial_acceptance_required" in capsys.readouterr().out


async def test_session_worker_reserves_individual_cases_and_allows_partial_budget(
    configured, monkeypatch,
):
    session, store, plan, snapshot, state, identity = configured
    # Key already spent 0.06: old whole-campaign check would reject before model.
    session.observe_gateway(info(spend=0.06), KEY, plan)
    run = cli.prepare_session(store, state, [plan.case_ids[1], plan.case_ids[2]])
    manifest = store.manifest(run)
    selected = EvalCampaignPlan.model_validate(manifest["plan"])
    gates = cli.approval_gates(selected, snapshot, identity)
    env = {**dict(os.environ), **gates}
    requested = []
    original = httpx.AsyncClient
    def handler(request):
        requested.append((request.method, request.url.path))
        if request.url.path == "/key/info":
            return httpx.Response(200, json={"info": info(spend=0.06)})
        return httpx.Response(200, json={"data": [{"id": plan.effective_gateway_route}]})
    class MockClient(original):
        def __init__(self, **kwargs):
            super().__init__(transport=httpx.MockTransport(handler), **kwargs)
    monkeypatch.setattr(httpx, "AsyncClient", MockClient)
    calls = []
    def executor(_plan, _snapshot, _env, recorder, **_kwargs):
        async def execute(request):
            calls.append(request.case.case_id)
            await recorder.record(event(plan))
            return EvalObservation(
                outcome="tool_call", tool_names=(request.case.required_tool,),
                requires_user_confirmation=request.case.requires_user_confirmation,
                reply=AgentReply(answer="Synthetic", proposal_text=""),
            )
        return type("Executor", (), {"execute": staticmethod(execute)})()
    monkeypatch.setattr(launch, "build_campaign_executor", executor)
    task = asyncio.create_task(cli.work(store, state, run, env))
    try:
        for case in selected.validate_snapshot(snapshot):
            for _ in range(100):
                if store.observation(run, case.case_id) or task.done():
                    break
                await asyncio.sleep(0.02)
            assert store.observation(run, case.case_id)
            for index in range(len(case.response_criteria)):
                store.review(run, case.case_id, index, "pass", "owner")
        await asyncio.wait_for(task, 5)
    finally:
        if not task.done():
            task.cancel()
            await task
    assert calls == list(selected.case_ids)
    assert store.status(run)["execution_status"] == "passed"
    assert Decimal(session.summary()["charged_or_reserved_usd"]) == Decimal("0.10")
    assert len(session.summary()["attempts"]) == 2
    assert all(method == "GET" for method, _ in requested)
    assert not (session.folder / "worker.lease").exists()
    with pytest.raises(ValueError, match="already_consumed"):
        await cli.work(store, state, run, env)


def test_concurrent_reservations_never_overdraw(configured):
    session, store, plan, *_ = configured
    session.observe_gateway(info(spend=0.08), KEY, plan)
    def reserve(index):
        try:
            EvalValidationSession(store).reserve(
                "c" * 32, plan.case_ids[index], SOURCE, Decimal("0.02"),
            )
            return True
        except EvalSessionError:
            return False
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(reserve, [0, 1]))
    assert results.count(True) == 1
    assert session.remaining() == 0


def test_overspend_is_not_hidden_by_missing_actual_cost(configured):
    session, _, plan, *_ = configured
    session.observe_gateway(info(spend=0), KEY, plan)
    session.reserve("c" * 32, plan.case_ids[0], SOURCE, Decimal("0.02"))
    with pytest.raises(EvalSessionError, match="cost_exceeded"):
        session.settle([event(plan, actual_cost=None, estimated_cost=0.021)], passed=True)
    assert session.summary()["attempts"][0]["status"] == "uncertain"
    assert session.summary()["charged_or_reserved_usd"] == "0.021"


def test_scope_key_expiry_and_corrupt_ciphertext_cannot_reset_session(configured):
    session, store, plan, snapshot, *_ = configured
    scope = session_scope(ROOT, plan, snapshot)
    original = session.path.read_bytes()
    for wrong_scope, wrong_key in [("f" * 64, KEY), (scope, "different")]:
        with pytest.raises(EvalSessionError, match="scope_or_key"):
            session.initialize(scope=wrong_scope, plan=plan, key=wrong_key, history=[])
        assert session.path.read_bytes() == original
    with store._lock(session.folder):
        value = session._read()
        value["expires"] = (datetime.now(UTC) - timedelta(seconds=1)).isoformat()
        session._save(value)
    with pytest.raises(EvalSessionError, match="expired"):
        session.summary()
    session.path.write_bytes(b"not-a-fernet-envelope")
    with pytest.raises(ValueError, match="corrupted"):
        session.initialize(scope=scope, plan=plan, key=KEY, history=[])


def test_scope_selection_cannot_change_model_or_enlarge_limits(configured):
    session, _, plan, *_ = configured
    for changes in ({"effective_gateway_route": "other-r1"}, {"config_revision": 9},
                    {"case_ids": ("response_style.unknown",)},
                    {"budget": plan.budget.model_copy(update={"max_model_calls": 7})}):
        with pytest.raises(EvalSessionError, match="scope_or_key"):
            session.validate_selection(plan.model_copy(update=changes), plan)


def test_history_missing_results_never_imports_zero_cost(configured):
    session, _, plan, *_ = configured
    with pytest.raises(EvalSessionError, match="history_unverifiable"):
        session.check_history([{"source": SOURCE, "results": []}], plan)


@pytest.mark.parametrize("pre_session_status", [None, "reserved", "running", "stopped"])
def test_cli_init_imports_history_once_and_never_starts_worker(
    configured, monkeypatch, capsys, pre_session_status,
):
    _, existing, plan, snapshot, state, identity = configured
    store = EvalEvidenceStore(state / "separate", Fernet.generate_key().decode())
    cases = plan.validate_snapshot(snapshot)
    old_identity = {**identity, "source_fingerprint": "d" * 64}
    old_run = store.create(old_identity, plan.model_dump(mode="json"),
                           [case_record(case) for case in cases],
                           snapshot.model_dump(mode="json", by_alias=True), synthetic_approved=True)
    results = [{"case_id": case.case_id, "status": "not_started"} for case in cases]
    results[0].update(status="passed")
    results[1].update(status="stopped", error_class="InvalidPresentationOutputError")
    report = {"status": "stopped", "plan_checksum": plan.checksum(),
              "cases_fingerprint": campaign_cases_fingerprint(cases),
              "source_fingerprint": old_identity["source_fingerprint"],
              "results": results, "usage": [{"status": "completed"}] * 5,
              "recorded_model_calls": 5}
    (state / (plan.checksum() + "." + "d" * 64 + ".report.json")).write_text(json.dumps(report))
    pre_session = state / (plan.checksum() + ".report.json")
    pre_session.write_text(json.dumps({"code_sha": cli.PRE_SESSION_SHA,
                                      "status": pre_session_status}))
    original_pre_session = pre_session.read_bytes()
    reservation = state / (plan.checksum() + ".reserved.json")
    reservation.write_text(json.dumps({"code_sha": cli.PRE_SESSION_SHA,
                                       "status": "consumed_do_not_replay"}))
    original_reservation = reservation.read_bytes()
    monkeypatch.setattr(cli, "store_from_env", lambda _: (store, state))
    monkeypatch.setattr(cli, "start_worker", lambda *_: pytest.fail("init must not infer"))
    requests = []
    def handler(request):
        requests.append(request)
        if request.url.path == "/key/info":
            return httpx.Response(200, json={"info": info(spend=0.005)})
        return httpx.Response(200, json={"data": [{"id": plan.effective_gateway_route}]})
    original = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: original(
        transport=httpx.MockTransport(handler), **kwargs,
    ))
    assert cli.main(["session-init", "--accept-session"]) == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["available_usd"] == "0.06"
    assert summary["gateway_spend_usd"] == "0.005"
    assert len(summary["attempts"]) == 2
    assert pre_session.read_bytes() == original_pre_session
    assert reservation.read_bytes() == original_reservation
    assert store.observation(old_run, cases[1].case_id) is None
    ledger = EvalValidationSession(store)
    initial_expiry = ledger.summary()["expires"]
    assert cli.main(["session-init", "--accept-session"]) == 0
    capsys.readouterr()
    assert ledger.summary()["expires"] == initial_expiry
    run = cli.prepare_session(store, state)
    manifest = store.manifest(run)
    assert manifest["plan"]["case_ids"] == list(plan.case_ids[1:])
    assert manifest["plan"]["budget"]["max_estimated_cost_usd"] == 0.015
    assert all(request.method == "GET" for request in requests)
    assert KEY not in json.dumps(summary)


async def test_real_governed_http_path_rechecks_key_and_stops_before_paid_request(
    configured, monkeypatch,
):
    from src.agent.ancora_agent import SafeOpenAILike

    session, store, plan, _, state, _ = configured
    session.observe_gateway(info(spend=0), KEY, plan)
    run = cli.prepare_session(store, state, [plan.case_ids[1]])
    key_reads = 0
    paid = 0
    def handler(request):
        nonlocal key_reads, paid
        if request.url.path == "/key/info":
            key_reads += 1
            return httpx.Response(200, json={"info": info(spend=0.10 if key_reads >= 2 else 0)})
        if request.url.path == "/v1/models":
            return httpx.Response(200, json={"data": [{"id": plan.effective_gateway_route}]})
        paid += 1
        pytest.fail("budget exhausted: paid request must never reach transport")
    original = httpx.AsyncClient
    class MockClient(original):
        def __init__(self, **kwargs):
            super().__init__(transport=httpx.MockTransport(handler), **kwargs)
    monkeypatch.setattr(httpx, "AsyncClient", MockClient)
    def resolve(**kwargs):
        return SafeOpenAILike, {"id": kwargs["model_id"], "base_url": kwargs["base_url"],
                                "api_key": kwargs["api_key"]}
    monkeypatch.setattr("src.agent.llm_access.resolve_model_parts", resolve)
    await cli.work(store, state, run, dict(os.environ))
    summary = store.status(run)
    assert summary["execution_status"] == "stopped" and key_reads >= 2 and paid == 0
    assert summary["cases"][0]["session_reason"] == "session_budget_insufficient"
    assert session.summary()["attempts"][0]["status"] == "uncertain"


async def test_request_guard_rejects_other_routes_and_keeps_current_reservation(configured):
    session, _, plan, snapshot, *_ = configured
    session.observe_gateway(info(spend=0), KEY, plan)
    session.reserve("c" * 32, plan.case_ids[0], SOURCE, Decimal("0.02"))
    context = ExecutionContext(
        correlation_id=uuid4(), telegram_update_id=0, agno_run_id="synthetic",
        agno_session_id="synthetic", config=snapshot,
        budget=ExecutionBudget.from_config(plan.budget, started_at_monotonic=0),
    )
    with execution_context_scope(context):
        with pytest.raises(EvalSessionError, match="paid_route"):
            await session.before_request(httpx.Request("POST", "http://gateway/v1/embeddings"))
        context.budget.estimated_cost_usd = 0.03
        with pytest.raises(EvalSessionError, match="insufficient"):
            await session.before_request(httpx.Request("POST", "http://gateway/v1/chat/completions"))


@pytest.mark.parametrize("fail_second_check", [False, True])
async def test_real_sdk_session_path_uses_pre_post_checks_without_retries(
    configured, monkeypatch, fail_second_check,
):
    from src.agent.ancora_agent import SafeOpenAILike

    session, store, plan, _, state, _ = configured
    session.observe_gateway(info(spend=0), KEY, plan)
    run = cli.prepare_session(store, state, [plan.case_ids[1]])
    paid = []
    reads = []
    def handler(request):
        if request.url.path == "/key/info":
            reads.append(True)
            if fail_second_check and paid:
                return httpx.Response(503, json={"error": "PRIVATE_GATEWAY_ERROR"})
            return httpx.Response(200, json={"info": info(spend=0.001 * len(paid))})
        if request.url.path == "/v1/models":
            return httpx.Response(200, json={"data": [{"id": plan.effective_gateway_route}]})
        assert request.url.path == "/v1/chat/completions" and request.method == "POST"
        body = json.loads(request.content)
        assert body["model"] == plan.effective_gateway_route
        paid.append(True)
        name, args = (
            ("propose_todo_item", {"list_id": "11111111-1111-1111-1111-111111111111",
                                   "title": "Synthetic", "priority": "high"})
            if len(paid) == 1 else
            ("present_reply", {"answer": "Synthetic tasks", "proposal_text": "Synthetic proposal"})
        )
        return httpx.Response(200, json={
            "id": "synthetic", "object": "chat.completion", "created": 0,
            "model": plan.effective_gateway_route,
            "choices": [{"index": 0, "finish_reason": "tool_calls", "message": {
                "role": "assistant", "content": None, "tool_calls": [{
                    "id": "call" + str(len(paid)), "type": "function",
                    "function": {"name": name, "arguments": json.dumps(args)},
                }],
            }}],
            "usage": {"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8},
        })
    original = httpx.AsyncClient
    class MockClient(original):
        def __init__(self, **kwargs):
            super().__init__(transport=httpx.MockTransport(handler), **kwargs)
    monkeypatch.setattr(httpx, "AsyncClient", MockClient)
    monkeypatch.setattr("src.agent.llm_access.resolve_model_parts", lambda **kw: (
        SafeOpenAILike, {"id": kw["model_id"], "base_url": kw["base_url"],
                        "api_key": kw["api_key"]},
    ))
    task = asyncio.create_task(cli.work(store, state, run, dict(os.environ)))
    try:
        for _ in range(100):
            if task.done() or store.observation(run, plan.case_ids[1]):
                break
            await asyncio.sleep(0.02)
        if not fail_second_check:
            assert store.observation(run, plan.case_ids[1])
            for i in range(2):
                store.review(run, plan.case_ids[1], i, "pass", "owner")
        await asyncio.wait_for(task, 5)
    finally:
        if not task.done():
            task.cancel()
            await task
    result = store.status(run)
    if fail_second_check:
        assert len(paid) == 1
        assert result["execution_status"] == "stopped"
        assert result["cases"][0]["session_reason"] == "session_budget_unverifiable"
        assert session.summary()["attempts"][0]["status"] == "uncertain"
    else:
        assert len(paid) == 2
        assert len(reads) == 5  # case start plus pre/post each physical request
        assert result["execution_status"] == "passed"
    assert KEY not in json.dumps(result) and "PRIVATE_GATEWAY_ERROR" not in json.dumps(result)


def test_orphan_legacy_reservation_blocks_import_even_with_other_valid_reports(configured):
    _, _, plan, _, state, _ = configured
    marker = state / (plan.checksum() + ".orphan.reserved.json")
    marker.write_text('{}')
    with pytest.raises(EvalSessionError, match="history_unverifiable"):
        cli.session_history(state, plan)


def test_ledger_projection_rejects_bad_fields_and_does_not_echo_extra(configured):
    session, store, plan, *_ = configured
    session.observe_gateway(info(spend=0), KEY, plan)
    session.reserve("c" * 32, plan.case_ids[0], SOURCE, Decimal("0.02"))
    with store._lock(session.folder):
        value = session._read()
        value["attempts"][0]["PRIVATE_EXTRA"] = "PRIVATE_SECRET_CONTENT"
        session._save(value)
    assert "PRIVATE" not in json.dumps(session.summary())
    with store._lock(session.folder):
        value = session._read()
        value["attempts"][0]["charged"] = "NaN"
        session._save(value)
    with pytest.raises(EvalSessionError, match="unverifiable"):
        session.summary()


def test_reserve_per_case_ceiling_cannot_expand_even_with_available_credit(configured):
    session, _, plan, *_ = configured
    session.observe_gateway(info(spend=0), KEY, plan)
    with pytest.raises(EvalSessionError, match="insufficient"):
        session.reserve("c" * 32, plan.case_ids[0], SOURCE, Decimal("0.03"))
    assert session.summary()["attempts"] == []


def test_unknown_or_running_history_blocks_instead_of_resetting_budget(configured):
    _, _, plan, snapshot, state, _ = configured
    path = state / (plan.checksum() + "." + SOURCE + ".report.json")
    path.write_text(json.dumps({"status": "running"}))
    with pytest.raises(EvalSessionError, match="not_terminal"):
        cli.session_history(state, plan)
    path.write_text(json.dumps({"status": "stopped", "plan_checksum": "bad"}))
    with pytest.raises(EvalSessionError, match="unverifiable"):
        cli.session_history(state, plan)


def test_scope_data_is_secret_free_but_not_a_signature(configured):
    session, _, plan, snapshot, *_ = configured
    old = session.path.read_bytes()
    session.validate(session_scope(ROOT, plan, snapshot), KEY)
    assert session.path.read_bytes() == old
    for entry in session.folder.iterdir():
        assert KEY.encode() not in entry.read_bytes()


async def test_insufficient_reservation_is_reported_before_any_model_or_case_review(
    configured, monkeypatch,
):
    session, store, plan, _, state, _ = configured
    session.observe_gateway(info(spend=0), KEY, plan)
    run = cli.prepare_session(store, state, [plan.case_ids[2]])
    original = httpx.AsyncClient
    def handler(request):
        assert request.method == "GET"
        if request.url.path == "/key/info":
            return httpx.Response(200, json={"info": info(spend=0.10)})
        return httpx.Response(200, json={"data": [{"id": plan.effective_gateway_route}]})
    class MockClient(original):
        def __init__(self, **kwargs):
            super().__init__(transport=httpx.MockTransport(handler), **kwargs)
    monkeypatch.setattr(httpx, "AsyncClient", MockClient)
    model_calls = []
    def build(*_args, **_kwargs):
        async def execute(_request):
            model_calls.append(True)
            pytest.fail("no funds: no model allowed")
        return type("Executor", (), {"execute": staticmethod(execute)})()
    monkeypatch.setattr(launch, "build_campaign_executor", build)
    await cli.work(store, state, run, dict(os.environ))
    status = store.status(run)
    assert status["execution_status"] == "stopped" and status["inference_started"] is False
    assert status["cases"][0]["session_reason"] == "session_budget_insufficient"
    assert status["cases"][0]["evidence_available"] is False
    assert model_calls == [] and session.summary()["attempts"] == []


def test_single_scope_import_reserves_uncertain_run_without_reconstruction(configured):
    _, store, plan, snapshot, *_ = configured
    other = EvalEvidenceStore(store.root.parent / "uncertain-import",
                              Fernet.generate_key().decode())
    session = EvalValidationSession(other)
    results = [{"case_id": case, "status": "not_started"} for case in plan.case_ids]
    results[1].update(status="stopped", error_class="TimeoutError")
    summary = session.initialize(scope=session_scope(ROOT, plan, snapshot), plan=plan, key=KEY,
                                 history=[{"source": SOURCE, "run_id": "c" * 32,
                                           "results": results, "usage_complete": False}])
    assert summary["attempts"][0]["status"] == "uncertain"
    assert summary["charged_or_reserved_usd"] == "0.02"
    session.observe_gateway(info(spend=0), KEY, plan)
    with pytest.raises(EvalSessionError, match="uncertain"):
        session.reserve("d" * 32, plan.case_ids[1], "e" * 64, Decimal("0.01"))


def test_failed_read_does_not_rebase_prior_spend_or_restore_credit(configured):
    session, _, plan, *_ = configured
    session.observe_gateway(info(spend=0.005), KEY, plan)
    session.reserve("c" * 32, plan.case_ids[0], SOURCE, Decimal("0.02"))
    session.settle([event(plan)], passed=True)
    session.gateway_error("session_budget_unverifiable")
    assert session.summary()["gateway_observed"] is False
    session.observe_gateway(info(spend=0.007), KEY, plan)
    assert session.summary()["charged_or_reserved_usd"] == "0.025"
    assert session.summary()["gateway_observed"] is True


@pytest.mark.parametrize("status", [None, "reserved", "running", "stopped", "passed"])
def test_known_pre_session_candidate_report_is_preserved_not_charged_again(configured, status):
    _, _, plan, snapshot, state, _ = configured
    old = state / (plan.checksum() + ".report.json")
    old.write_text(json.dumps({"status": status, "code_sha": cli.PRE_SESSION_SHA,
                               "source_fingerprint": "d" * 64}))
    assert cli.session_history(state, plan) == []
    assert old.exists()
    current = state / (plan.checksum() + "." + SOURCE + ".report.json")
    current.write_text(json.dumps({
        "status": "stopped", "code_sha": "a" * 40, "source_fingerprint": SOURCE,
        "plan_checksum": plan.checksum(),
        "cases_fingerprint": campaign_cases_fingerprint(plan.validate_snapshot(snapshot)),
        "results": [{"case_id": case, "status": "not_started"} for case in plan.case_ids],
        "recorded_model_calls": 0, "usage": [],
    }))
    history = cli.session_history(state, plan)
    assert len(history) == 1 and history[0]["source"] == SOURCE
    assert old.exists() and current.exists()


@pytest.mark.parametrize("sha", ["a" * 40, "7ea0cf06002d76692f230d189c43e8f9f5e742b1", None])
@pytest.mark.parametrize("status", [None, "reserved", "running", "consumed_do_not_replay"])
def test_excluding_pre_session_report_never_skips_current_or_unknown_active_report(
    configured, sha, status,
):
    session, _, plan, _, state, _ = configured
    old = state / (plan.checksum() + ".report.json")
    old.write_text(json.dumps({"code_sha": cli.PRE_SESSION_SHA, "status": "reserved"}))
    current = state / (plan.checksum() + "." + SOURCE + ".report.json")
    current.write_text(json.dumps({"code_sha": sha, "status": status}))
    original = {path: path.read_bytes() for path in (old, current, session.path)}
    with pytest.raises(EvalSessionError, match="session_prior_execution_not_terminal"):
        cli.session_history(state, plan)
    assert all(path.read_bytes() == raw for path, raw in original.items())


@pytest.mark.parametrize("payload", [[], None, "PRIVATE_REPORT_NOT_AN_OBJECT"])
def test_history_non_object_remains_blocked_without_echoing_contents(configured, payload):
    _, _, plan, _, state, _ = configured
    path = state / (plan.checksum() + ".report.json")
    path.write_text(json.dumps(payload))
    with pytest.raises(EvalSessionError, match="session_history_unverifiable") as error:
        cli.session_history(state, plan)
    assert "PRIVATE" not in str(error.value)


def test_same_source_different_subset_cannot_bypass_completed_selection(configured):
    session, store, plan, _, state, _ = configured
    session.observe_gateway(info(spend=0), KEY, plan)
    cli.prepare_session(store, state, [plan.case_ids[0]])
    session.reserve("c" * 32, plan.case_ids[0], SOURCE, Decimal("0.02"))
    session.settle([event(plan)], passed=True)
    with pytest.raises(FileExistsError):
        cli.prepare_session(store, state, [plan.case_ids[1]])


def test_partial_known_actual_overspend_is_preserved_even_with_other_unknown_cost(configured):
    session, _, plan, *_ = configured
    session.observe_gateway(info(spend=0), KEY, plan)
    session.reserve("c" * 32, plan.case_ids[0], SOURCE, Decimal("0.02"))
    with pytest.raises(EvalSessionError, match="cost_exceeded"):
        session.settle([event(plan, actual_cost=0.021), event(plan, actual_cost=None)],
                       passed=False)
    assert session.summary()["attempts"][0]["status"] == "uncertain"
    assert session.summary()["charged_or_reserved_usd"] == "0.021"
