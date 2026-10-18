"""One paid-smoke authorization does not authorize a campaign or replays."""

import io
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest

from scripts import eval_accounting_smoke as smoke

KEY = "sk-synthetic-never-real"
MASTER = "sk-synthetic-master-never-real"
KEY_ALIAS = smoke.PREFIX + "synthetic"


def info(spend=0):
    return {
        "key_alias": KEY_ALIAS, "expires": (datetime.now(UTC) + timedelta(minutes=25)).isoformat(),
        "models": [smoke.ALIAS], "allowed_routes": smoke.SMOKE_ROUTES,
        "max_budget": 0.01, "budget_duration": None, "budget_reset_at": None,
        "spend": spend, "max_parallel_requests": 1, "rpm_limit": 1, "tpm_limit": 2000,
    }


@pytest.fixture
def prepared(tmp_path, monkeypatch):
    from scripts import eval_source, execute_eval_campaign
    monkeypatch.setattr(smoke, "ROOT", Path(__file__).resolve().parents[2])
    monkeypatch.setattr(smoke, "STATE", tmp_path)
    monkeypatch.setattr(eval_source, "source_identity", lambda _: {
        "code_sha": smoke.SHA, "source_fingerprint": smoke.SOURCE,
        "identity_source": "sealed_image", "worktree": "clean",
    })
    monkeypatch.setattr(execute_eval_campaign, "validate_state_directory", lambda *_a, **_k: None)
    return {
        "ANCORA_EVAL_ACCOUNTING_SMOKE_APPROVED": "one-call-0.01-usd",
        "ANCORA_EVAL_GATEWAY_URL": "http://litellm.railway.internal:4000/v1",
    }, tmp_path


@pytest.mark.parametrize("failure", [None, "http", "connection", "spend_missing"])
async def test_real_llm_access_exactly_one_post_and_reservation_blocks_replay(
    prepared, failure, monkeypatch,
):
    env, state = prepared
    posts = []
    async def fast_sleep(_):
        pass
    monkeypatch.setattr(smoke.asyncio, "sleep", fast_sleep)
    def handler(request):
        if request.method == "GET":
            if request.url.path == "/key/info":
                return httpx.Response(200, json={"info": info(
                    0.0001 if posts and failure != "spend_missing" else 0,
                )})
            return httpx.Response(200, json={"data": [{"id": smoke.ALIAS}]})
        body = json.loads(request.content)
        posts.append(body)
        assert body["model"] == smoke.ALIAS and body["max_tokens"] == 64
        assert body["num_retries"] == 0 and body["fallbacks"] == []
        assert body["provider"] == {"allow_fallbacks": False}
        assert not body.get("tools") and not body.get("stream")
        assert (state / smoke.RESERVATION).exists()
        if failure == "http":
            return httpx.Response(503, json={"error": {"message": "synthetic " + KEY}})
        if failure == "connection":
            raise httpx.ReadTimeout("synthetic " + KEY, request=request)
        return httpx.Response(200, headers={"x-litellm-response-cost": "0.0001"}, json={
            "id": "synthetic", "object": "chat.completion", "created": 1,
            "model": smoke.ALIAS, "choices": [{"index": 0,
                "message": {"role": "assistant", "content": "PRIVATE_SYNTHETIC_REPLY"},
                "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12},
        })
    transport = httpx.MockTransport(handler)
    report = await smoke.smoke(env, KEY, transport=transport)
    assert len(posts) == 1
    assert report["campaign_approved"] is False
    if failure is None:
        assert report["status"] == "smoke_accounting_verified"
        assert report["spend_delta_usd"] == "0.0001"
    elif failure == "spend_missing":
        assert report["status"] == "smoke_spend_not_observed_do_not_replay"
    else:
        assert report["status"] == "smoke_failed_or_ambiguous_do_not_replay"
    text = json.dumps(report) + (state / smoke.REPORT).read_text()
    assert KEY not in text and "PRIVATE_SYNTHETIC_REPLY" not in text
    with pytest.raises((FileExistsError, ValueError)):
        await smoke.smoke(env, KEY, transport=transport)
    assert len(posts) == 1


async def test_no_approval_no_files_no_http(prepared):
    env, state = prepared
    env.pop("ANCORA_EVAL_ACCOUNTING_SMOKE_APPROVED")
    with pytest.raises(ValueError, match="approval_required"):
        await smoke.smoke(env, KEY, transport=httpx.MockTransport(
            lambda _: pytest.fail("no network"),
        ))
    assert list(state.iterdir()) == []


def test_admin_keeps_key_only_in_private_console_and_revokes(monkeypatch, capsys):
    monkeypatch.setenv("LITELLM_MASTER_KEY", MASTER)
    class Console(io.StringIO):
        def isatty(self):
            return True
    console = Console()
    calls = []
    created_alias = None
    def call(method, route, token, payload=None):
        nonlocal created_alias
        calls.append((method, route, token, payload))
        if route == "/key/generate":
            created_alias = payload["key_alias"]
            assert payload["max_budget"] == 0.01 and payload["duration"] == "30m"
            return {"key": KEY}
        if route == "/key/info":
            return {"info": {**info(), "key_alias": created_alias}}
        if route == "/v1/models":
            return {"data": [{"id": smoke.ALIAS}]}
        if route == "/key/delete":
            assert payload == {"keys": [KEY]}
            return {"deleted_keys": [KEY]}
        assert "key_alias=" + created_alias in route
        return {"total_count": 0}
    assert smoke.admin(console, io.StringIO("\n"), call) == 0
    assert KEY in console.getvalue()
    output = capsys.readouterr().out
    assert KEY not in output and MASTER not in output
    assert '"smoke_key_revoked_verified"' in output
    assert sum(route == "/key/generate" for _, route, _, _ in calls) == 1


@pytest.mark.parametrize("override", [
    {"allowed_routes": ["llm_api_routes"]}, {"max_budget": 0.10}, {"spend": "NaN"},
    {"models": []}, {"expires": (datetime.now(UTC) - timedelta(seconds=1)).isoformat()},
    {"permissions": {"admin": True}},
])
def test_bad_key_restrictions_rejected(override):
    with pytest.raises(ValueError):
        smoke.key_metadata({**info(), **override}, datetime.now(UTC))


def test_failed_admin_verification_revokes_new_key_without_delivering(monkeypatch, capsys):
    monkeypatch.setenv("LITELLM_MASTER_KEY", MASTER)
    class Console(io.StringIO):
        def isatty(self):
            return True
    console = Console()
    calls = []
    def call(method, route, token, payload=None):
        calls.append(route)
        if route == "/key/generate":
            return {"key": KEY}
        if route == "/key/info":
            return {"info": {**info(), "max_budget": 20}}
        if route == "/key/delete":
            return {"deleted_keys": [KEY]}
        return {"total_count": 0}
    assert smoke.admin(console, io.StringIO("\n"), call) == 1
    assert KEY not in console.getvalue()
    output = capsys.readouterr().out
    assert KEY not in output and MASTER not in output
    assert "smoke_key_revoked_verified" in output
    assert calls == ["/key/generate", "/key/info", "/key/delete", calls[-1]]
