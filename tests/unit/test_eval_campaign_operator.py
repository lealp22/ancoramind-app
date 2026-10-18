"""Operator wiring reuses sealed campaign, human console and one-shot reservation."""

import io
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest

from scripts import eval_accounting_smoke as operator
from scripts import execute_eval_campaign as cli
from src.agent.evals import EvalObservation
from src.domain.interactions.reply import AgentReply
from src.domain.llm_access.models import LlmUsageEventCreate

KEY = "sk-synthetic-campaign-not-real"
KEY_ALIAS = operator.CAMPAIGN_POLICY.prefix + "synthetic"


class Console(io.StringIO):
    def isatty(self):
        return True

    def close(self):
        if not self.closed:
            self.transcript = self.getvalue()
        super().close()


def key_info():
    return {
        "key_alias": KEY_ALIAS, "models": [operator.ALIAS],
        "allowed_routes": operator.SMOKE_ROUTES,
        "expires": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
        "max_budget": 0.10, "spend": 0, "max_parallel_requests": 1,
        "rpm_limit": 30, "tpm_limit": 250000,
    }


@pytest.fixture
def prepared(tmp_path, monkeypatch):
    from scripts import eval_source

    monkeypatch.setattr(operator, "ROOT", Path(__file__).resolve().parents[2])
    monkeypatch.setattr(operator, "STATE", tmp_path)
    monkeypatch.setattr(eval_source, "source_identity", lambda *_: {
        "code_sha": operator.SHA, "source_fingerprint": operator.SOURCE,
        "worktree": "clean", "identity_source": "sealed_image",
    })
    monkeypatch.setattr(cli, "validate_state_directory", lambda *_a, **_k: None)
    return {
        "ANCORA_EVAL_CAMPAIGN_OPERATOR_APPROVED": "five-cases-0.10-usd-once",
        "ANCORA_EVAL_GATEWAY_URL": "http://litellm.railway.internal:4000/v1",
    }, tmp_path


@pytest.mark.parametrize("label", ["p", "f", "x"])
async def test_existing_runner_human_review_one_shot_checkpoint_and_no_content_leak(
    prepared, monkeypatch, capsys, label,
):
    env, state = prepared
    executor_calls = []
    def handler(request):
        assert request.method == "GET"
        return httpx.Response(200, json={"info": {
            **key_info(), "spend": 0.0001 if executor_calls else 0,
        }})
    transport = httpx.MockTransport(handler)
    original_client = httpx.AsyncClient
    # Intercept only HTTP I/O of the original launcher; keep reservation and runner real.
    monkeypatch.setattr(cli.httpx, "AsyncClient", lambda **kwargs: original_client(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json={
            "data": [{"id": operator.ALIAS}],
        })), **kwargs,
    ) if "transport" not in kwargs else original_client(**kwargs))
    monkeypatch.setattr(cli, "source_identity", lambda: {
        "code_sha": operator.SHA, "source_fingerprint": operator.SOURCE,
        "worktree": "clean", "identity_source": "sealed_image",
    })
    writer = Console()
    monkeypatch.setattr(cli, "open_review_console", lambda: (Console((label + "\n") * 12), writer))
    def build(plan, snapshot, approved_env, recorder, **kwargs):
        assert approved_env["ANCORA_EVAL_APPROVED_SHA"] == operator.SHA
        assert approved_env["ANCORA_EVAL_APPROVED_CASES"] == operator.CASES
        async def execute(request):
            assert (state / (operator.PLAN + ".reserved.json")).exists()
            executor_calls.append(request.case.case_id)
            await recorder.record(LlmUsageEventCreate(
                interaction_id=uuid4(), llm_call_id=uuid4(), config_revision=8,
                logical_route=plan.logical_route, effective_gateway_route=operator.ALIAS,
                estimated_cost=0.001, status="completed",
            ))
            return EvalObservation(
                outcome="tool_call", tool_names=(request.case.required_tool,),
                requires_user_confirmation=request.case.requires_user_confirmation,
                reply=AgentReply(answer="PRIVATE_SYNTHETIC_REPLY", proposal_text=""),
            )
        return type("SyntheticExecutor", (), {"execute": staticmethod(execute)})()
    monkeypatch.setattr(cli, "build_campaign_executor", build)
    report = await operator.campaign(env, KEY, transport=transport)
    assert len(executor_calls) == (5 if label == "p" else 1)
    assert report["status"] == ("passed" if label == "p" else "stopped")
    assert report["gateway_spend"]["status"] == "observed"
    assert report["gateway_spend"]["delta_usd"] == "0.0001"
    assert report["campaign_approved"] is True and report["permission_cleanup_required"] is True
    assert KEY not in json.dumps(report) and "PRIVATE_SYNTHETIC" not in json.dumps(report)
    assert "PRIVATE_SYNTHETIC" in writer.transcript  # only explicit reviewer console
    assert not capsys.readouterr().out
    for path in state.iterdir():
        assert KEY not in path.read_text() and "PRIVATE_SYNTHETIC" not in path.read_text()
    with pytest.raises(ValueError, match="already_consumed"):
        await operator.campaign(env, KEY, transport=transport)
    assert len(executor_calls) == (5 if label == "p" else 1)


async def test_no_operator_approval_no_io(prepared, monkeypatch):
    env, state = prepared
    env.pop("ANCORA_EVAL_CAMPAIGN_OPERATOR_APPROVED")
    monkeypatch.setattr(cli, "execute_approved", AsyncMock(
        side_effect=AssertionError("no execute"),
    ))
    with pytest.raises(ValueError, match="explicit_approval"):
        await operator.campaign(env, KEY, transport=httpx.MockTransport(
            lambda _: pytest.fail("no network"),
        ))
    assert list(state.iterdir()) == []


def test_campaign_admin_budget_expiry_scope_and_cleanup(monkeypatch, capsys):
    monkeypatch.setenv("LITELLM_MASTER_KEY", "synthetic-master")
    calls = []
    created_alias = None
    def call(method, route, token, payload=None):
        nonlocal created_alias
        calls.append(route)
        if route == "/key/generate":
            assert payload["models"] == [operator.ALIAS]
            assert payload["max_budget"] == 0.10 and payload["duration"] == "2h"
            assert payload["max_parallel_requests"] == 1
            assert payload["allowed_routes"] == operator.SMOKE_ROUTES
            created_alias = payload["key_alias"]
            return {"key": KEY}
        if route == "/key/info":
            return {"info": {**key_info(), "key_alias": created_alias}}
        if route == "/v1/models":
            return {"data": [{"id": operator.ALIAS}]}
        if route == "/key/delete":
            assert payload == {"keys": [KEY]}
            return {"deleted_keys": [KEY]}
        assert "key_alias=" + created_alias in route
        return {"total_count": 0}
    console = Console()
    assert operator.admin(console, io.StringIO("\n"), call,
                          policy=operator.CAMPAIGN_POLICY) == 0
    output = capsys.readouterr().out
    assert "campaign_key_ready" in output and "campaign_key_revoked_verified" in output
    assert KEY not in output and KEY in console.getvalue()
    assert calls.count("/key/generate") == calls.count("/key/delete") == 1


async def test_smoke_key_cannot_be_reused_for_campaign(prepared, monkeypatch):
    env, state = prepared
    launch = AsyncMock()
    monkeypatch.setattr(cli, "execute_approved", launch)
    transport = httpx.MockTransport(lambda _: httpx.Response(200, json={"info": {
        **key_info(), "key_alias": operator.PREFIX + "synthetic", "max_budget": 0.01,
    }}))
    with pytest.raises(ValueError, match="restrictions_mismatch"):
        await operator.campaign(env, KEY, transport=transport)
    launch.assert_not_awaited()
    assert list(state.iterdir()) == []


async def test_new_key_with_existing_marker_does_not_relaunch_campaign(prepared, monkeypatch):
    env, state = prepared
    marker = state / (operator.PLAN + ".reserved.json")
    marker.write_text('{"status":"consumed_do_not_replay"}')
    launch = AsyncMock()
    monkeypatch.setattr(cli, "execute_approved", launch)
    with pytest.raises(ValueError, match="already_consumed"):
        await operator.campaign(env, KEY, transport=httpx.MockTransport(
            lambda _: pytest.fail("no network after existing marker"),
        ))
    launch.assert_not_awaited()
    assert marker.exists()
