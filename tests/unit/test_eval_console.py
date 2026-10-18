"""Detached lifecycle and review commands; no real credentials or inference."""

import io
import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import httpx
import pytest
from cryptography.fernet import Fernet

from scripts import eval_console as cli
from scripts.execute_eval_campaign import validate_live_approval
from src.agent.eval_campaign import EvalCampaignPlan
from src.agent.eval_campaign_runner import campaign_cases_fingerprint
from src.agent.eval_durable_review import DurableCampaignReviewer
from src.agent.evals import EvalObservation
from src.domain.interactions.reply import AgentReply
from src.domain.runtime_config.models import RuntimeConfigSnapshot

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def configured(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "validate_state_directory", lambda *_a, **_k: None)
    monkeypatch.setenv("ANCORA_EVAL_STATE_DIR", str(tmp_path))
    key = Fernet.generate_key().decode()
    monkeypatch.setenv("ANCORA_EVAL_EVIDENCE_KEY", key)
    monkeypatch.setenv("ANCORA_EVAL_GATEWAY_URL", "http://gateway.railway.internal:4000/v1")
    monkeypatch.setenv("ANCORA_EVAL_GATEWAY_KEY", "fixture-placeholder-not-real")
    folder = ROOT / "evals/response_style"
    plan = EvalCampaignPlan.model_validate_json((folder / "bl48-campaign-plan.json").read_text())
    snapshot = RuntimeConfigSnapshot.model_validate_json(
        (folder / "runtime-rev8-snapshot.json").read_text()
    )
    identity = {"code_sha": "a" * 40, "source_fingerprint": "b" * 64,
                "worktree": "clean", "identity_source": "sealed_image"}
    monkeypatch.setattr(cli, "source_identity", lambda: identity)
    gates = {
        "ANCORA_EVAL_APPROVED_PLAN": plan.checksum(), "ANCORA_EVAL_APPROVED_SHA": "a" * 40,
        "ANCORA_EVAL_APPROVED_SOURCE": "b" * 64,
        "ANCORA_EVAL_APPROVED_CASES": campaign_cases_fingerprint(plan.validate_snapshot(snapshot)),
        "ANCORA_EVAL_SYNTHETIC_APPROVED": "1", "ANCORA_EVAL_EXTERNAL_BUDGET_VERIFIED": "1",
        "ANCORA_EVAL_SNAPSHOT_PROVENANCE_ACCEPTED": "1",
        "ANCORA_EVAL_HUMAN_REVIEW_APPROVED": "1",
    }
    path = tmp_path / "approval.json"
    path.write_text(json.dumps({"evidence_synthetic_approved": True, "gates": gates}))
    store, state = cli.store_from_env(dict(os.environ))
    return store, state, path, plan, snapshot


def test_detached_worker_contains_no_secret_in_args_and_no_inference_before_start(monkeypatch):
    process = Mock(pid=123)
    popen = Mock(return_value=process)
    monkeypatch.setattr(cli.subprocess, "Popen", popen)
    assert cli.start_worker("a" * 32) == 123
    args, kwargs = popen.call_args
    assert args[0][-3:] == ["worker", "--run", "a" * 32]
    assert kwargs["stdin"] == cli.subprocess.DEVNULL
    assert kwargs["stdout"] == kwargs["stderr"] == cli.subprocess.DEVNULL
    assert kwargs.get("start_new_session") or kwargs.get("creationflags")


async def test_worker_uses_exact_saved_approval_and_never_restarts(configured, monkeypatch):
    store, state, path, plan, snapshot = configured
    run = cli.prepare(store, state, path)
    async def execute(plan_arg, snap_arg, identity, env, state_arg, *, durable):
        assert plan_arg == plan and snap_arg == snapshot
        assert durable[1] == run
        validate_live_approval(
            plan_arg, identity, campaign_cases_fingerprint(plan_arg.validate_snapshot(snap_arg)),
            env,
        )
        return {"status": "stopped"}
    launch = AsyncMock(side_effect=execute)
    monkeypatch.setattr(cli, "execute_approved", launch)
    monkeypatch.setattr(cli, "validate_reusable_access", AsyncMock())
    await cli.work(store, state, run, {"ANCORA_EVAL_GATEWAY_KEY": "PRIVATE_ONLY_IN_PROCESS"})
    with pytest.raises(ValueError, match="no_restart"):
        await cli.work(store, state, run, {})
    assert launch.await_count == 1
    assert "PRIVATE_ONLY_IN_PROCESS" not in json.dumps(store.events(run))


@pytest.mark.parametrize("alter", ["secret", "wrong_sha", "missing_synthetic"])
def test_prepare_rejects_unapproved_or_secret_gate_file(configured, alter):
    store, state, path, *_ = configured
    raw = json.loads(path.read_text())
    if alter == "secret":
        raw["gates"]["ANCORA_EVAL_GATEWAY_KEY"] = "PRIVATE_KEY"
    elif alter == "wrong_sha":
        raw["gates"]["ANCORA_EVAL_APPROVED_SHA"] = "c" * 40
    else:
        raw["evidence_synthetic_approved"] = False
    path.write_text(json.dumps(raw))
    with pytest.raises(ValueError):
        cli.prepare(store, state, path)
    assert not list(store.root.glob("*.reserved"))


def test_prior_campaign_marker_is_never_automatically_replayed(configured):
    store, state, path, plan, _ = configured
    marker = state / (plan.checksum() + ".reserved.json")
    marker.write_text(json.dumps({"source_fingerprint": "b" * 64}))
    with pytest.raises(ValueError, match="consumed"):
        cli.prepare(store, state, path)
    assert marker.exists()


async def test_status_list_review_label_promote_commands_do_not_resolve_provider(
    configured, monkeypatch, capsys,
):
    store, state, path, plan, snapshot = configured
    run = cli.prepare(store, state, path)
    case = plan.validate_snapshot(snapshot)[0]
    DurableCampaignReviewer(store, run).capture(case, EvalObservation(
        outcome="tool_call", reply=AgentReply(answer="", proposal_text="Propuesta privada."),
        proposals=(), tool_trace=(), delivered_text="Texto privado",
    ), {"passed": True})
    monkeypatch.setattr(cli, "execute_approved", AsyncMock(
        side_effect=AssertionError("no inference"),
    ))
    class Console(io.StringIO):
        def isatty(self):
            return True
    monkeypatch.setattr(cli, "open_review_console", lambda: (Console("p\np\n"), Console()))
    assert cli.main(["status", "--run", run]) == 0
    assert cli.main(["list"]) == 0
    # Calling review_saved directly avoids waiting for the future cases not yet executed.
    from src.agent.eval_durable_review import review_saved
    await review_saved(store, run, "owner", Console("p\np\n"), Console())
    assert cli.main(["label", "--run", run, "--case", case.case_id,
                     "--criterion", "1", "--label", "fail", "--comment", "synthetic"]) == 0
    assert cli.main(["promote", "--run", run, "--case", case.case_id,
                     "--dataset", "judge", "--split", "validation", "--sanitized-approved"]) == 0
    output = capsys.readouterr().out
    assert "privad" not in output and "synthetic" not in output


def test_human_review_evidence_saved_even_before_deterministic_failure(configured):
    store, _, path, plan, snapshot = configured
    run = cli.prepare(store, configured[1], path)
    case = plan.validate_snapshot(snapshot)[0]
    reviewer = DurableCampaignReviewer(store, run)
    reviewer.capture(case, EvalObservation(outcome="no_tool_call", reply=AgentReply(
        answer="No hice la propuesta.", proposal_text="",
    )), {"passed": False})
    assert store.observation(run, case.case_id)["verdict"]["passed"] is False


@pytest.mark.parametrize("bad", [None, "scope", "budget", "expiry", "reset", "overrides"])
async def test_reusable_key_is_read_only_validated_without_resetting_budget(
    configured, monkeypatch, bad,
):
    _, _, _, plan, _ = configured
    observed = []
    def handler(request):
        observed.append(request)
        assert request.method == "GET"
        if request.url.path == "/v1/models":
            return httpx.Response(200, json={"data": [{"id": "ancoramind-default-r4"}]})
        info = {
            "expires": (datetime.now(UTC) + timedelta(days=7)).isoformat(),
            "models": ["ancoramind-default-r4"], "spend": 0.01, "max_budget": 0.20,
            "key_alias": "ancoramind-evals-reusable", "max_parallel_requests": 1,
            "allowed_routes": ["/v1/models", "/key/info", "/v1/chat/completions"],
        }
        info.update({
            "scope": {"models": []}, "budget": {"spend": 0.19},
            "expiry": {"expires": (datetime.now(UTC) - timedelta(seconds=1)).isoformat()},
            "reset": {"budget_duration": "1d"}, "overrides": {"config": {"other": "model"}},
        }.get(bad, {}))
        return httpx.Response(200, json={"info": info})
    original = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: original(
        transport=httpx.MockTransport(handler), **kwargs,
    ))
    env = {"ANCORA_EVAL_GATEWAY_URL": "http://gateway.railway.internal:4000/v1",
           "ANCORA_EVAL_GATEWAY_KEY": "synthetic"}
    if bad is None:
        await cli.validate_reusable_access(plan, env)
        assert len(observed) == 2
    else:
        with pytest.raises(ValueError):
            await cli.validate_reusable_access(plan, env)
