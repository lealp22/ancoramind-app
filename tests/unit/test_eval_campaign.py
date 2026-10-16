"""T7 preparation never infers, persists or silently falls back to a provider."""

import json
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import AsyncMock

import httpx
import pytest

from scripts.eval_preflight import main
from src.agent.eval_campaign import (
    EvalCampaignPlan,
    EvalUsageRecorder,
    build_campaign_executor,
    gateway_settings,
)
from src.agent.eval_physical_executor import eval_snapshot_fingerprint
from src.domain.llm_access.models import LlmUsageEventCreate
from src.domain.runtime_config.models import (
    RuntimeConfigSnapshot,
    bootstrap_runtime_configuration,
    config_checksum,
)


@pytest.fixture
def snapshot():
    raw = bootstrap_runtime_configuration().model_dump(mode="json", by_alias=True)
    raw["routing"]["routes"]["ancoramind-default"]["effective_gateway_route"] = "eval-test-r1"
    raw["pricing"] = {
        "routes": {"eval-test-r1": {"input_cost_per_1m_usd": 0.1, "output_cost_per_1m_usd": 0.5}}
    }
    raw["cost_governance"] = {
        "external_hard_limit_usd": 1,
        "daily_budget_usd": 0.1,
        "monthly_budget_usd": 1,
        "alert_threshold_pct": 60,
        "strong_alert_threshold_pct": 80,
        "hard_stop_threshold_pct": 90,
    }
    raw["execution_budget"]["max_estimated_cost_usd"] = 0.1
    config = type(bootstrap_runtime_configuration()).model_validate(raw)
    return RuntimeConfigSnapshot(
        revision=8, source="database", checksum=config_checksum(config), config=config
    )


@pytest.fixture
def plan(snapshot):
    budget = snapshot.config.execution_budget.model_dump()
    budget.update(
        max_model_calls=4, max_gateway_requests=4, max_gateway_attempts_per_model_call=1,
        max_estimated_cost_usd=0.02,
    )
    return EvalCampaignPlan(
        version=1,
        logical_route="ancoramind-default",
        effective_gateway_route="eval-test-r1",
        snapshot_checksum=snapshot.checksum,
        snapshot_fingerprint=eval_snapshot_fingerprint(snapshot),
        config_revision=8,
        case_ids=("response_style.single_proposal", "response_style.tasks_after_discard"),
        budget=budget,
        total_estimated_cost_usd="0.04",
    )


def test_pure_plan_validation_needs_no_secrets_or_network(plan, snapshot):
    assert len(plan.validate_snapshot(snapshot)) == 2
    assert plan.metadata()["semantic_status"] == "not_evaluated"
    assert plan.metadata()["plan_checksum"] == plan.checksum()


@pytest.mark.parametrize("field,value", [
    ("config_revision", 7), ("snapshot_checksum", "0" * 64),
    ("snapshot_fingerprint", "0" * 64),
    ("effective_gateway_route", "other-r1"), ("total_estimated_cost_usd", "0.01"),
    ("case_ids", ["response_style.unknown"]),
    ("case_ids", ["response_style.single_proposal", "response_style.single_proposal"]),
    ("case_ids", ["response_style.brief_question"]),
])
def test_invalid_plan_fails_before_wiring(plan, snapshot, field, value):
    raw = plan.model_dump(mode="json")
    raw[field] = value
    with pytest.raises(ValueError):
        EvalCampaignPlan.model_validate(raw).validate_snapshot(snapshot)


def test_budget_cannot_expand_or_remove_cost_ceiling(plan, snapshot):
    for value in (None, 0.2):
        raw = plan.model_dump(mode="json")
        raw["budget"]["max_estimated_cost_usd"] = value
        with pytest.raises(ValueError):
            EvalCampaignPlan.model_validate(raw).validate_snapshot(snapshot)


@pytest.mark.parametrize("gateway", [
    "https://openrouter.ai/v1", "https://api.openai.com/v1", "http://public.example/v1",
    "http://user:secret@localhost/v1", "http://localhost/v1?key=secret",
    "http://localhost/other", "http://localhost/v1#secret", "",
])
def test_gateway_rejects_direct_public_or_credential_urls(gateway):
    with pytest.raises(ValueError, match="eval_private_gateway_required"):
        gateway_settings({"ANCORA_EVAL_GATEWAY_URL": gateway, "ANCORA_EVAL_GATEWAY_KEY": "test"})


def test_gateway_ignores_ambient_secrets_and_database(monkeypatch):
    monkeypatch.setenv("ANCORA_DATABASE_URL", "postgresql://should-not-be-used")
    monkeypatch.setenv("OPENROUTER_API_KEY", "ambient-sensitive-key")
    monkeypatch.setenv("TELEGRAM_TOKEN", "123456:ambient-sensitive-token")
    monkeypatch.setenv("REMINDER_WORKER_ENABLED", "true")
    settings = gateway_settings({
        "ANCORA_EVAL_GATEWAY_URL": "http://127.0.0.1:4000/v1",
        "ANCORA_EVAL_GATEWAY_KEY": "eval-sensitive-key",
    })
    assert settings.litellm_proxy_enabled
    assert settings.openrouter_api_key == ""
    assert settings.ancora_database_url == settings.telegram_token == ""
    assert not settings.reminder_worker_enabled


def test_wiring_requires_plan_bound_approval(plan, snapshot):
    with pytest.raises(ValueError, match="explicit_approval"):
        build_campaign_executor(plan, snapshot, {}, EvalUsageRecorder())


def test_approved_wiring_creates_no_agent_provider_or_inference(plan, snapshot, monkeypatch):
    model_for = AsyncMock(side_effect=AssertionError("no inference in wiring"))
    monkeypatch.setattr("src.agent.eval_campaign.AgnoLLMAccess.model_for", model_for)
    recorder = EvalUsageRecorder()
    executor = build_campaign_executor(plan, snapshot, {
        "ANCORA_EVAL_APPROVED_PLAN": plan.checksum(),
        "ANCORA_EVAL_SYNTHETIC_APPROVED": "1",
        "ANCORA_EVAL_EXTERNAL_BUDGET_VERIFIED": "1",
        "ANCORA_EVAL_GATEWAY_URL": "http://gateway.railway.internal:4000/v1",
        "ANCORA_EVAL_GATEWAY_KEY": "synthetic-key",
    }, recorder)
    assert executor._snapshot == snapshot
    assert executor._budget == plan.budget
    assert recorder.metadata() == []
    model_for.assert_not_called()


async def test_usage_projection_contains_no_text_or_provider_ids():
    from uuid import uuid4

    recorder = EvalUsageRecorder()
    await recorder.record(LlmUsageEventCreate(
        interaction_id=uuid4(), llm_call_id=uuid4(), config_revision=8,
        logical_route="ancoramind-default", effective_gateway_route="eval-test-r1",
        status="completed", provider_request_id="sensitive-provider-id", model="sensitive-model",
    ))
    serialized = json.dumps(recorder.metadata())
    assert "sensitive" not in serialized
    assert "response_text" not in serialized


def test_cli_dry_run_never_contacts_gateway(plan, snapshot, tmp_path, capsys, monkeypatch):
    path = tmp_path / "snapshot.json"
    path.write_text(snapshot.model_dump_json(by_alias=True), encoding="utf-8")
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(plan.model_dump_json(), encoding="utf-8")
    monkeypatch.setattr(httpx.Client, "get", lambda *a, **k: pytest.fail("network in dry-run"))
    assert main(["--snapshot", str(path), "--plan", str(plan_path)]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["inference_started"] is False
    assert output["gateway_access"] == "not_checked"
    assert output["approval_status"] == "pending_separate_approval"


@pytest.mark.parametrize("aliases,status,exit_code", [
    (["eval-test-r1"], 200, 0), (["other-r1"], 200, 1),
    (["eval-test-r1", "other-r1"], 200, 1), ([], 401, 1),
])
def test_cli_gateway_check_is_get_only_and_key_is_restricted(
    plan, snapshot, tmp_path, capsys, monkeypatch, aliases, status, exit_code
):
    path = tmp_path / "snapshot.json"
    path.write_text(snapshot.model_dump_json(by_alias=True), encoding="utf-8")
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(plan.model_dump_json(), encoding="utf-8")
    monkeypatch.setenv("ANCORA_EVAL_GATEWAY_URL", "http://localhost:4000/v1")
    monkeypatch.setenv("ANCORA_EVAL_GATEWAY_KEY", "sensitive-credential")

    def get(client, url, **kwargs):
        assert url == "http://localhost:4000/v1/models"
        assert client.follow_redirects is False
        return httpx.Response(status, json={"data": [{"id": alias} for alias in aliases]})

    monkeypatch.setattr(httpx.Client, "get", get)
    assert main(["--snapshot", str(path), "--plan", str(plan_path), "--check-gateway"]) == exit_code
    assert "sensitive-credential" not in capsys.readouterr().out


def test_versioned_candidate_and_fingerprint_are_stable_across_processes():
    root = Path(__file__).resolve().parents[2]
    snapshot_path = root / "evals" / "response_style" / "runtime-rev8-snapshot.json"
    plan_path = snapshot_path.with_name("bl48-campaign-plan.json")
    snapshot = RuntimeConfigSnapshot.model_validate_json(snapshot_path.read_text(encoding="utf-8"))
    plan = EvalCampaignPlan.model_validate_json(plan_path.read_text(encoding="utf-8"))
    assert len(plan.validate_snapshot(snapshot)) == 5
    for seed in ("1", "2"):
        env = {**os.environ, "PYTHONHASHSEED": seed}
        result = subprocess.run(  # noqa: S603 - repository script, fixed args, no shell
            [sys.executable, str(root / "scripts" / "eval_preflight.py"),
             "--snapshot", str(snapshot_path), "--plan", str(plan_path)],
            cwd=root, env=env, capture_output=True, text=True, timeout=30, check=False,
        )
        assert result.returncode == 0
        assert json.loads(result.stdout)["snapshot_fingerprint"] == plan.snapshot_fingerprint


async def test_real_llm_access_wiring_uses_gateway_with_simulated_tools_only(
    plan, snapshot, monkeypatch
):
    from src.agent.ancora_agent import SafeOpenAILike
    from src.agent.evals import EvalExecutionRequest

    recorder = EvalUsageRecorder()
    requests = []

    def handler(request):
        assert str(request.url) == "http://gateway.railway.internal:4000/v1/chat/completions"
        body = json.loads(request.content)
        assert body["model"] == "eval-test-r1"
        assert body["max_tokens"] == plan.budget.max_output_tokens
        assert body["tool_choice"] == "required"
        assert "response_format" not in body
        names = {tool["function"]["name"] for tool in body["tools"]}
        assert not any(name.startswith("execute_") for name in names)
        name, args = (
            ("propose_todo_item", {
                "list_id": "11111111-1111-1111-1111-111111111111",
                "title": "Revisar póliza", "priority": "high",
            }) if not requests else (
                "present_reply", {"answer": "", "proposal_text": "Propuesta creada."}
            )
        )
        requests.append(body)
        return httpx.Response(200, json={
            "id": "synthetic", "object": "chat.completion", "created": 0, "model": "eval-test-r1",
            "choices": [{"index": 0, "finish_reason": "tool_calls", "message": {
                "role": "assistant", "content": None, "tool_calls": [{
                    "id": f"call-{len(requests)}", "type": "function",
                    "function": {"name": name, "arguments": json.dumps(args)},
                }],
            }}],
            "usage": {"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8},
        })

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        def resolve(**kwargs):
            assert kwargs["provider"] == "openai-like"
            return SafeOpenAILike, {
                "id": kwargs["model_id"], "base_url": kwargs["base_url"],
                "api_key": kwargs["api_key"], "http_client": client,
            }

        monkeypatch.setattr("src.agent.llm_access.resolve_model_parts", resolve)
        executor = build_campaign_executor(plan, snapshot, {
            "ANCORA_EVAL_APPROVED_PLAN": plan.checksum(),
            "ANCORA_EVAL_SYNTHETIC_APPROVED": "1",
            "ANCORA_EVAL_EXTERNAL_BUDGET_VERIFIED": "1",
            "ANCORA_EVAL_GATEWAY_URL": "http://gateway.railway.internal:4000/v1",
            "ANCORA_EVAL_GATEWAY_KEY": "synthetic-key",
        }, recorder)
        case = plan.validate_snapshot(snapshot)[0]
        observation = await executor.execute(EvalExecutionRequest(
            case=case, logical_route=plan.logical_route, config_revision=plan.config_revision
        ))
    assert observation.tool_names == ("propose_todo_item",)
    assert observation.requires_user_confirmation
    assert len(requests) == len(recorder.events) == 2
    assert {event.config_revision for event in recorder.events} == {8}
    assert {event.effective_gateway_route for event in recorder.events} == {"eval-test-r1"}
    assert all(event.status == "completed" and event.retry_count == 0 for event in recorder.events)

