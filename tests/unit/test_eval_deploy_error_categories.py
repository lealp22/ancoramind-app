"""Fixed diagnostic categories, not arbitrary CLI output, may cross the boundary."""

import json
import subprocess
from unittest.mock import Mock

import pytest

from scripts import deploy_eval_candidate as deploy


@pytest.mark.parametrize("message,category", [
    ("Unauthorized. Please check that your RAILWAY_TOKEN is valid and has access to the "
     "resource you're trying to use.", "authorization_denied"),
    ("Invalid RAILWAY_TOKEN. Please check that it is valid and has access to the resource "
     "you're trying to use.", "project_token_not_found"),
    ("You do not have access to this resource.", "authorization_denied"),
    ("Not signed in.", "authentication_missing"),
    ("Login state is corrupt. Please logout and login back in.", "credential_header_invalid"),
    ("Project not found. Run `railway link` to connect to a project.", "project_not_found"),
    ("Project is deleted. Run `railway link` to connect to a project.", "project_deleted"),
    ("Environment is deleted. Run `railway environment` to connect to an environment.",
     "environment_deleted"),
    ("No linked project found. Run railway link to connect to a project", "linked_project_missing"),
    ("You are being ratelimited. Please try again later", "rate_limited"),
    ("Failed to fetch: SYNTHETIC_PRIVATE", "transport_or_response_error"),
    ("Failed to get data from GraphQL response", "response_data_missing"),
    ('Cannot query field "SYNTHETIC_PRIVATE" on type "PRIVATE_TYPE".', "graphql_schema_error"),
    ("Cannot return null for non-nullable field SYNTHETIC_PRIVATE",
     "graphql_response_contract_error"),
    ("error decoding response body: SYNTHETIC_PRIVATE", "response_decode_error"),
])
@pytest.mark.parametrize("prefix", ["", "Error: "])
def test_cli_human_errors_become_only_fixed_categories(message, category, prefix):
    assert deploy.railway_error_category("", prefix + message, 1) == category


@pytest.mark.parametrize("code,category", [
    ("UNAUTHORIZED_TOKEN", "authorization_denied"), ("INVALID_TOKEN", "project_token_not_found"),
    ("INVALID_HEADER", "credential_header_invalid"), ("PROJECT_NOT_FOUND", "project_not_found"),
    ("ENVIRONMENT_NOT_FOUND", "environment_not_found"),
    ("ENVIRONMENT_RESTRICTED", "environment_restricted"),
    ("RATELIMITED", "rate_limited"), ("FETCH_ERROR", "transport_or_response_error"),
    ("GRAPHQL_ERROR", "graphql_error"), ("MISSING_RESPONSE_DATA", "response_data_missing"),
])
@pytest.mark.parametrize("stream", ["stdout", "stderr"])
def test_cli_structured_errors_never_return_message_or_hint(code, category, stream):
    payload = json.dumps({"code": code, "error": "SYNTHETIC_PRIVATE", "hint": "SYNTHETIC_PRIVATE"})
    assert deploy.railway_error_category(payload if stream == "stdout" else "",
                                         payload if stream == "stderr" else "", 1) == category


@pytest.mark.parametrize("payload", [
    "SYNTHETIC_PRIVATE", "", "[]", "null", "false", "1", "{{",
    '{"code":"UNAUTHORIZED_TOKEN","error":null}',
    '{"code":"SYNTHETIC_PRIVATE","error":"SYNTHETIC_PRIVATE"}',
    '{"code":[],"error":"SYNTHETIC_PRIVATE"}',
    '{"code":"UNAUTHORIZED_TOKEN","data":"SYNTHETIC_PRIVATE"}',
    'prefix Unauthorized. SYNTHETIC_PRIVATE',
    '[{"code":"UNAUTHORIZED_TOKEN","error":"SYNTHETIC_PRIVATE"}]',
])
def test_unknown_or_malformed_data_remains_unclassified(payload):
    assert deploy.railway_error_category(payload, payload, 1) == "unclassified"


@pytest.mark.parametrize("category,message", [
    ("authorization_denied", "Unauthorized. SYNTHETIC_PRIVATE"),
    ("project_token_not_found", "Invalid RAILWAY_TOKEN. SYNTHETIC_PRIVATE"),
    ("graphql_schema_error", 'Cannot query field "SYNTHETIC_PRIVATE" on type "PRIVATE".'),
    ("response_decode_error", "error decoding response body: SYNTHETIC_PRIVATE"),
    ("unclassified", "SYNTHETIC_PRIVATE"),
])
def test_inventory_failure_summary_classifies_without_raw_output_or_retry(
    monkeypatch, tmp_path, capsys, category, message,
):
    monkeypatch.setattr(deploy.sys, "platform", "linux")
    monkeypatch.setattr(deploy.shutil, "which", lambda _: "/runner/railway")
    monkeypatch.setenv("RAILWAY_TOKEN", "synthetic")
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    run = Mock(return_value=subprocess.CompletedProcess([], 1, stdout="", stderr=message))
    monkeypatch.setattr(deploy.subprocess, "run", run)
    def publish(*args, **kwargs):
        deploy.Railway("synthetic").status()
    monkeypatch.setattr(deploy, "publish", publish)
    assert deploy.main(["publish", "--directory", str(tmp_path)]) == 1
    output = capsys.readouterr()
    report = json.loads(output.out)
    assert report["phase"] == "inventory"
    assert report["reason"] == "eval_deploy_railway_command_failed"
    assert report["command_exit_code"] == 1
    assert report["command_error_category"] == category
    assert "PRIVATE" not in output.out + output.err + summary.read_text(encoding="utf-8")
    assert run.call_count == 1
    assert run.call_args.args[0] == ["/runner/railway", "status", *deploy.TARGET, "--json"]
    environment = run.call_args.kwargs["env"]
    assert environment["RAILWAY_NO_TELEMETRY"] == "1"
    assert environment["RAILWAY_NO_AUTO_UPDATE"] == "1"


def test_usage_error_does_not_need_raw_arg_or_path():
    assert deploy.railway_error_category("", "SYNTHETIC_PRIVATE", 2) == "cli_usage_error"
