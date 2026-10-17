"""Access-check diagnostics expose only fixed stages/classes and HTTP status."""

import io
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest

from scripts import check_eval_gateway_access as check

KEY = "sk-synthetic-private-no-credential"


@pytest.fixture
def prepared(monkeypatch):
    from scripts import eval_source

    class Console(io.StringIO):
        def isatty(self):
            return True

    monkeypatch.setattr(check, "open", lambda *_a, **_k: Console(), raising=False)
    monkeypatch.setattr(check.getpass, "getpass", lambda *_a, **_k: KEY)
    monkeypatch.setattr(eval_source, "source_identity", lambda _: {
        "code_sha": check.SHA, "source_fingerprint": check.SOURCE,
        "identity_source": "sealed_image", "worktree": "clean",
    })
    monkeypatch.setattr(check, "ROOT", Path(__file__).resolve().parents[2])
    monkeypatch.setenv("ANCORA_EVAL_GATEWAY_URL", "http://litellm.railway.internal:4000/v1")
    original_client = httpx.Client
    requests = []

    def install(handler):
        def respond(request):
            requests.append(request)
            assert request.method == "GET"
            assert request.url.path in {"/v1/models", "/key/info"}
            return handler(request)
        monkeypatch.setattr(httpx, "Client", lambda **kwargs: original_client(
            transport=httpx.MockTransport(respond), **kwargs,
        ))

    return install, requests


def read_report(capsys):
    output = capsys.readouterr()
    assert KEY not in output.out + output.err
    assert "Bearer" not in output.out + output.err
    return json.loads(output.out)


def test_missing_url_reports_configuration_stage_not_a_network_error(prepared, monkeypatch, capsys):
    monkeypatch.delenv("ANCORA_EVAL_GATEWAY_URL")
    assert check.main() == 1
    report = read_report(capsys)
    assert report["stage"] == "gateway_settings"
    assert report["error_class"] == "ValueError"
    assert report["gateway_url_present"] is False
    assert report["http_status"] is None
    assert prepared[1] == []


@pytest.mark.parametrize("status", [401, 403, 404, 429, 500, 302])
def test_models_http_status_without_response_body_or_credentials(prepared, capsys, status):
    install, requests = prepared
    install(lambda request: httpx.Response(status, json={"error": KEY}, request=request))
    assert check.main() == 1
    report = read_report(capsys)
    assert report["stage"] == "models_response"
    assert report["error_class"] == "HTTPStatusError"
    assert report["http_status"] == status
    assert len(requests) == 1


def test_connection_error_not_confused_with_bad_key(prepared, capsys):
    install, _ = prepared
    def fail(request):
        raise httpx.ConnectError("private exception " + KEY, request=request)
    install(fail)
    assert check.main() == 1
    report = read_report(capsys)
    assert report["stage"] == "models_request"
    assert report["error_class"] == "ConnectError"
    assert report["http_status"] is None


def test_model_scope_failure_stops_before_key_info(prepared, capsys):
    install, requests = prepared
    install(lambda _: httpx.Response(200, json={"data": [{"id": "wrong-model"}]}))
    assert check.main() == 1
    report = read_report(capsys)
    assert report["stage"] == "models_scope"
    assert report["error_class"] == "ValueError"
    assert report["http_status"] == 200
    assert len(requests) == 1


def test_info_endpoint_failure_has_its_own_stage(prepared, capsys):
    install, requests = prepared
    def respond(request):
        if request.url.path == "/v1/models":
            return httpx.Response(200, json={"data": [{"id": "ancoramind-default-r4"}]})
        return httpx.Response(403, json={"error": KEY})
    install(respond)
    assert check.main() == 1
    report = read_report(capsys)
    assert report["stage"] == "key_info_response"
    assert report["http_status"] == 403
    assert len(requests) == 2


def test_success_preserves_read_only_checks(prepared, capsys):
    install, requests = prepared
    def respond(request):
        if request.url.path == "/v1/models":
            return httpx.Response(200, json={"data": [{"id": "ancoramind-default-r4"}]})
        return httpx.Response(200, json={"key": KEY, "info": {
            "expires": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
            "models": ["ancoramind-default-r4"], "allowed_routes": sorted(check.ROUTES),
            "max_budget": 0.10, "spend": 0, "max_parallel_requests": 1,
            "rpm_limit": 30, "tpm_limit": 250000,
            "key_alias": "ancoramind-evals-access-synthetic",
        }})
    install(respond)
    assert check.main() == 0
    report = read_report(capsys)
    assert report["status"] == "eval_gateway_read_only_verified"
    assert report["inference_started"] is report["inference_enabled"] is False
    assert len(requests) == 2


def test_expired_key_response_is_not_misreported_as_connection_failure(prepared, capsys):
    install, requests = prepared
    def respond(request):
        if request.url.path == "/v1/models":
            return httpx.Response(200, json={"data": [{"id": "ancoramind-default-r4"}]})
        return httpx.Response(200, json={"info": {
            "expires": (datetime.now(UTC) - timedelta(hours=1)).isoformat(),
        }})
    install(respond)
    assert check.main() == 1
    report = read_report(capsys)
    assert report["stage"] == "key_info_restrictions"
    assert report["http_status"] == 200
    assert report["error_class"] == "ValueError"
    assert len(requests) == 2


def test_unknown_exception_class_cannot_leak_secret(prepared, monkeypatch, capsys):
    def fail(*_a, **_k):
        raise type(KEY, (Exception,), {})(KEY)
    monkeypatch.setattr(check.getpass, "getpass", fail)
    assert check.main() == 1
    report = read_report(capsys)
    assert report["stage"] == "key_input"
    assert report["error_class"] == "OtherError"
    assert prepared[1] == []
