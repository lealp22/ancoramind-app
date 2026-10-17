"""Temporary access provisioning is loopback-only and cannot authorize inference."""

import copy
import io
import json
import threading
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from scripts import provision_eval_gateway_key as cli
from scripts.check_eval_gateway_access import verified_info

NOW = datetime(2026, 10, 17, tzinfo=UTC)
KEY = "sk-synthetic-eval-key-not-a-credential"
MASTER = "sk-synthetic-master-not-a-credential"


def api(overrides=None):
    calls = []
    def call(base, method, route, key, payload):
        calls.append((base, method, route, key, copy.deepcopy(payload)))
        if route == "/key/generate":
            return {"key": KEY}
        if route == "/key/info":
            return {"info": {
                "key_alias": "synthetic", "models": [cli.ALIAS],
                "allowed_routes": cli.READ_ROUTES, "max_budget": 0.1, "spend": 0,
                "budget_duration": None, "budget_reset_at": None,
                "max_parallel_requests": 1, "rpm_limit": 30, "tpm_limit": 250000,
                "expires": (NOW + timedelta(hours=2)).isoformat(), **(overrides or {}),
            }}
        if route == "/key/delete":
            return {"deleted_keys": [KEY], "failed_tokens": []}
        return {"data": [{"id": cli.ALIAS}]}
    return calls, call


def test_persisted_scope_budget_expiry_verified_no_inference_or_secret_in_report():
    calls, call = api()
    delivered = []
    report = cli.provision({"PORT": "4000", "LITELLM_MASTER_KEY": MASTER}, call,
                           delivered.append, NOW, "synthetic")
    assert delivered == [KEY]
    assert report["status"] == "eval_key_read_only_ready"
    assert report["inference_started"] is report["inference_enabled"] is False
    assert report["pricing_verified"] is False
    assert KEY not in json.dumps(report) and MASTER not in json.dumps(report)
    assert sum(c[2] == "/key/generate" for c in calls) == 1
    assert all(c[0] == "http://127.0.0.1:4000" for c in calls)
    assert all(c[2] in {"/v1/models", "/key/generate", "/key/info"} for c in calls)
    payload = next(c[4] for c in calls if c[2] == "/key/generate")
    assert payload["models"] == [cli.ALIAS] and payload["budget_duration"] is None
    assert "llm_api_routes" not in payload["allowed_routes"]


@pytest.mark.parametrize("override", [
    {"max_budget": 20}, {"models": []}, {"spend": 0.01}, {"budget_duration": "30d"},
    {"allowed_routes": ["llm_api_routes"]}, {"max_parallel_requests": 4},
    {"expires": (NOW + timedelta(days=30)).isoformat()}, {"expires": None},
    {"aliases": {"extra": "model"}}, {"permissions": {"admin": True}},
    {"blocked": True}, {"auto_rotate": True},
])
def test_widened_or_missing_restriction_revokes_only_new_key(override):
    calls, call = api(override)
    with pytest.raises(cli.ProvisionError, match="created_key_revoked"):
        cli.provision({"LITELLM_MASTER_KEY": MASTER}, call,
                      lambda _: pytest.fail("must not deliver"), NOW, "synthetic")
    assert calls[-1][2:] == ("/key/delete", MASTER, {"keys": [KEY]})


def test_unknown_creation_never_retried_or_delivered():
    calls = []
    def call(base, method, route, key, payload):
        calls.append(route)
        if route == "/key/generate":
            raise TimeoutError("synthetic ambiguous error")
        return {"data": [{"id": cli.ALIAS}]}
    with pytest.raises(TimeoutError):
        cli.provision({"LITELLM_MASTER_KEY": MASTER}, call,
                      lambda _: pytest.fail("must not deliver"), NOW, "synthetic")
    assert calls == ["/v1/models", "/key/generate"]


def test_serialized_empty_prisma_json_fields_are_not_permissions():
    _, call = api({"aliases": "{}", "config": "{}", "permissions": "{}"})
    report = cli.provision({"LITELLM_MASTER_KEY": MASTER}, call,
                           lambda _: None, NOW, "synthetic")
    assert report["inference_enabled"] is False


def test_failed_delivery_revokes_new_key_and_never_repeats_creation():
    calls, call = api()
    def fail(_):
        raise OSError("synthetic console unavailable")
    with pytest.raises(cli.ProvisionError, match="created_key_revoked"):
        cli.provision({"LITELLM_MASTER_KEY": MASTER}, call, fail, NOW, "synthetic")
    assert calls[-1][2:] == ("/key/delete", MASTER, {"keys": [KEY]})
    assert sum(c[2] == "/key/generate" for c in calls) == 1


def test_missing_master_or_bad_port_does_not_call_gateway():
    for env in ({}, {"LITELLM_MASTER_KEY": MASTER, "PORT": "4000/evil"}):
        with pytest.raises(cli.ProvisionError):
            cli.provision(env, lambda *_: pytest.fail("no request"),
                          lambda _: pytest.fail("no secret"), NOW, "synthetic")


def test_key_goes_only_to_explicit_private_console(capsys):
    console = io.StringIO()
    cli.deliver_console(console, KEY)
    assert KEY in console.getvalue()
    assert KEY not in capsys.readouterr().out


def test_eval_check_reports_only_metadata_and_rejects_inference_routes():
    _, call = api()
    info = call("", "GET", "/key/info", KEY, None)["info"]
    info["key_alias"] = "ancoramind-evals-access-synthetic"
    result = verified_info(info, NOW)
    assert result["max_budget_usd"] == "0.10"
    assert KEY not in json.dumps(result)
    info["allowed_routes"] = ["llm_api_routes"]
    with pytest.raises(ValueError, match="restrictions_mismatch"):
        verified_info(info, NOW)


def test_eval_check_rejects_serialized_permission_overrides():
    _, call = api()
    info = call("", "GET", "/key/info", KEY, None)["info"]
    info["key_alias"] = "ancoramind-evals-access-synthetic"
    info["permissions"] = '{"admin": true}'
    with pytest.raises(ValueError, match="overrides_forbidden"):
        verified_info(info, NOW)


def test_request_transport_blocks_redirects_proxies_and_inference(monkeypatch):
    requests = []
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802 - stdlib HTTP server interface
            requests.append(self.path)
            self.send_response(302)
            self.send_header("Location", "/unexpected")
            self.end_headers()

        def log_message(self, *_):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = "http://127.0.0.1:" + str(server.server_port)
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:1")
    try:
        with pytest.raises(cli.ProvisionError, match="http_failed"):
            cli.request_local(base, "GET", "/v1/models", KEY, None)
        with pytest.raises(cli.ProvisionError, match="route_forbidden"):
            cli.request_local(base, "POST", "/v1/chat/completions", KEY, {})
        with pytest.raises(cli.ProvisionError, match="route_forbidden"):
            cli.request_local("https://example.com", "GET", "/v1/models", KEY, None)
        assert requests == ["/v1/models"]
    finally:
        server.shutdown()
        thread.join(timeout=3)
        server.server_close()
