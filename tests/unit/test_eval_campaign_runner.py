"""Real campaign boundaries tested with synthetic executors, never paid inference."""

import asyncio
import io
import json
from pathlib import Path
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest

from scripts import execute_eval_campaign as cli
from src.agent.eval_campaign import EvalCampaignPlan, EvalUsageRecorder
from src.agent.eval_campaign_runner import (
    EvalCampaignRunner,
    TerminalCampaignReviewer,
    campaign_cases_fingerprint,
)
from src.agent.evals import EvalObservation
from src.domain.interactions.reply import AgentReply
from src.domain.llm_access.models import LlmUsageEventCreate
from src.domain.runtime_config.models import RuntimeConfigSnapshot

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def campaign():
    folder = ROOT / "evals" / "response_style"
    snapshot = RuntimeConfigSnapshot.model_validate_json(
        (folder / "runtime-rev8-snapshot.json").read_text(encoding="utf-8")
    )
    plan = EvalCampaignPlan.model_validate_json(
        (folder / "bl48-campaign-plan.json").read_text(encoding="utf-8")
    )
    return plan, snapshot


def usage(plan, **changes):
    data = dict(
        interaction_id=uuid4(), llm_call_id=uuid4(), config_revision=8,
        logical_route=plan.logical_route, effective_gateway_route=plan.effective_gateway_route,
        status="completed", estimated_cost=0.001,
    )
    data.update(changes)
    return LlmUsageEventCreate(**data)


def observation(case):
    return EvalObservation(
        outcome="tool_call", tool_names=(case.required_tool,),
        requires_user_confirmation=case.requires_user_confirmation,
        response_text="PRIVATE_SYNTHETIC_RESPONSE",
        reply=AgentReply(answer="PRIVATE_SYNTHETIC_RESPONSE", proposal_text=""),
    )


def runner(campaign, *, event_changes=None, labels=None, error=None, missing_usage=False):
    plan, snapshot = campaign
    recorder = EvalUsageRecorder()

    async def execute(request):
        if not missing_usage:
            await recorder.record(usage(plan, **(event_changes or {})))
        if error:
            raise error
        return observation(request.case)

    executor = AsyncMock()
    executor.execute.side_effect = execute
    reviewer = AsyncMock()
    reviewer.review.side_effect = lambda c, o: tuple(labels or ["pass"] * len(c.response_criteria))
    run = EvalCampaignRunner(
        plan=plan, snapshot=snapshot, executor=executor, recorder=recorder,
        reviewer=reviewer, code_sha="a" * 40,
    )
    return run, executor, reviewer


async def test_five_cases_once_reserved_before_work_report_has_no_content(campaign):
    run, executor, reviewer = runner(campaign)
    assert run.report["reserved_estimated_cost_usd"] == "0.10"
    executor.execute.assert_not_called()
    checkpoints = []
    report = await run.run(checkpoint=lambda r: checkpoints.append(json.dumps(r)))
    assert report["status"] == report["semantic_status"] == "passed"
    assert executor.execute.await_count == reviewer.review.await_count == 5
    assert report["recorded_model_calls"] == 5
    assert "PRIVATE_SYNTHETIC" not in json.dumps(report)
    assert "PRIVATE_SYNTHETIC" not in "".join(checkpoints)
    case = campaign[0].validate_snapshot(campaign[1])[0]
    assert "PRIVATE_SYNTHETIC" not in repr(observation(case))
    with pytest.raises(ValueError, match="already_consumed"):
        await run.run()
    assert executor.execute.await_count == 5


@pytest.mark.parametrize("error", [RuntimeError("PRIVATE_ERROR"), asyncio.CancelledError()])
async def test_failure_and_cancellation_stop_and_never_retry(campaign, error):
    run, executor, reviewer = runner(campaign, error=error)
    report = await run.run()
    assert report["status"] == "stopped"
    assert [r["status"] for r in report["results"]] == ["stopped"] + ["not_started"] * 4
    assert executor.execute.await_count == 1
    reviewer.review.assert_not_called()
    assert "PRIVATE_ERROR" not in json.dumps(report)


@pytest.mark.parametrize("changes", [
    {"estimated_cost": 0.021}, {"estimated_cost": None}, {"actual_cost": 0.021},
    {"status": "error"}, {"retry_count": 1}, {"fallback_used": True},
    {"config_revision": 7}, {"effective_gateway_route": "other-r1"},
])
async def test_usage_violations_stop_before_review_or_next_case(campaign, changes):
    run, executor, reviewer = runner(campaign, event_changes=changes)
    assert (await run.run())["status"] == "stopped"
    assert executor.execute.await_count == 1
    reviewer.review.assert_not_called()


async def test_missing_usage_never_certifies_a_case(campaign):
    run, executor, reviewer = runner(campaign, missing_usage=True)
    assert (await run.run())["status"] == "stopped"
    assert executor.execute.await_count == 1
    reviewer.review.assert_not_called()


async def test_partial_actual_cost_still_blocks_on_known_overspend(campaign):
    run, executor, reviewer = runner(campaign)
    async def execute(request):
        await run._recorder.record(usage(campaign[0], actual_cost=0.021))
        await run._recorder.record(usage(campaign[0], actual_cost=None))
        return observation(request.case)
    executor.execute.side_effect = execute
    assert (await run.run())["status"] == "stopped"
    assert executor.execute.await_count == 1
    reviewer.review.assert_not_called()


async def test_unknown_tool_name_never_leaks_into_report(campaign):
    run, executor, reviewer = runner(campaign)
    async def execute(request):
        await run._recorder.record(usage(campaign[0]))
        return EvalObservation(outcome="tool_call", tool_names=("PRIVATE_TOOL_STRING",))
    executor.execute.side_effect = execute
    report = await run.run()
    assert report["status"] == "stopped"
    assert "PRIVATE_TOOL_STRING" not in json.dumps(report)
    reviewer.review.assert_not_called()


def test_source_identity_changes_with_rubric_and_normalizes_line_endings(tmp_path):
    import shutil
    import subprocess
    executable = shutil.which("git")
    assert executable is not None
    def git(*args):
        return subprocess.run(  # noqa: S603 - fixed test git commands, no shell
            [executable, *args], cwd=tmp_path, check=True, capture_output=True,
        )
    git("init")
    git("-c", "user.name=Synthetic", "-c", "user.email=synthetic@example.invalid",
        "commit", "--allow-empty", "-m", "Synthetic fixture")
    for folder in ("src", "scripts", "prompts", "evals"):
        (tmp_path / folder).mkdir()
    path = tmp_path / "evals" / "cases.json"
    path.write_bytes(b'{"synthetic":true}\r\n')
    initial = cli.source_identity(tmp_path)
    path.write_bytes(b'{"synthetic":true}\n')
    assert cli.source_identity(tmp_path)["source_fingerprint"] == initial["source_fingerprint"]
    path.write_bytes(b'{"synthetic":false}\n')
    assert cli.source_identity(tmp_path)["source_fingerprint"] != initial["source_fingerprint"]


@pytest.mark.parametrize("labels", [["fail", "pass"], ["not_evaluated", "pass"], ["pass"]])
async def test_human_failure_or_missing_criterion_stops_remaining_inference(campaign, labels):
    run, executor, reviewer = runner(campaign, labels=labels)
    report = await run.run()
    assert report["status"] == "stopped"
    assert executor.execute.await_count == reviewer.review.await_count == 1


async def test_deterministic_failure_cannot_be_overridden_by_human(campaign):
    run, executor, reviewer = runner(campaign)
    executor.execute.side_effect = None
    executor.execute.return_value = EvalObservation(outcome="no_tool_call")
    await run._recorder.record(usage(campaign[0]))
    # Per-case usage starts fresh. Supply a row with the incorrect observation.
    async def execute(request):
        await run._recorder.record(usage(campaign[0]))
        return EvalObservation(outcome="no_tool_call")
    executor.execute.side_effect = execute
    report = await run.run()
    assert report["results"][0]["deterministic_status"] == "failed"
    reviewer.review.assert_not_called()


async def test_source_change_stops_before_inference(campaign):
    run, executor, reviewer = runner(campaign)
    async def changed():
        raise ValueError("sources_changed")
    assert (await run.run(before_case=changed))["status"] == "stopped"
    executor.execute.assert_not_called()
    reviewer.review.assert_not_called()


async def test_failed_checkpoint_does_not_spend(campaign):
    run, executor, reviewer = runner(campaign)
    def broken(report):
        raise OSError("disk_full")
    with pytest.raises(OSError):
        await run.run(checkpoint=broken)
    executor.execute.assert_not_called()
    reviewer.review.assert_not_called()


def approval(plan, snapshot):
    identity = {"code_sha": "a" * 40, "source_fingerprint": "b" * 64, "worktree": "clean"}
    cases_hash = campaign_cases_fingerprint(plan.validate_snapshot(snapshot))
    env = {
        "ANCORA_EVAL_APPROVED_PLAN": plan.checksum(),
        "ANCORA_EVAL_APPROVED_SHA": identity["code_sha"],
        "ANCORA_EVAL_APPROVED_SOURCE": identity["source_fingerprint"],
        "ANCORA_EVAL_APPROVED_CASES": cases_hash,
        "ANCORA_EVAL_SYNTHETIC_APPROVED": "1",
        "ANCORA_EVAL_EXTERNAL_BUDGET_VERIFIED": "1",
        "ANCORA_EVAL_SNAPSHOT_PROVENANCE_ACCEPTED": "1",
        "ANCORA_EVAL_HUMAN_REVIEW_APPROVED": "1",
        "ANCORA_EVAL_GATEWAY_URL": "http://127.0.0.1:4000/v1",
        "ANCORA_EVAL_GATEWAY_KEY": "PRIVATE_KEY",
    }
    return identity, env


@pytest.mark.parametrize("gate", [
    "ANCORA_EVAL_APPROVED_PLAN", "ANCORA_EVAL_APPROVED_SHA", "ANCORA_EVAL_APPROVED_SOURCE",
    "ANCORA_EVAL_APPROVED_CASES", "ANCORA_EVAL_SYNTHETIC_APPROVED",
    "ANCORA_EVAL_EXTERNAL_BUDGET_VERIFIED", "ANCORA_EVAL_SNAPSHOT_PROVENANCE_ACCEPTED",
    "ANCORA_EVAL_HUMAN_REVIEW_APPROVED",
])
async def test_missing_approval_has_no_files_network_or_inference(campaign, gate, tmp_path):
    plan, snapshot = campaign
    identity, env = approval(plan, snapshot)
    env.pop(gate)
    with pytest.raises(ValueError):
        await cli.execute_approved(plan, snapshot, identity, env, tmp_path)
    assert list(tmp_path.iterdir()) == []


async def test_dirty_commit_not_approved(campaign, tmp_path):
    plan, snapshot = campaign
    identity, env = approval(plan, snapshot)
    identity["worktree"] = "dirty"
    with pytest.raises(ValueError):
        await cli.execute_approved(plan, snapshot, identity, env, tmp_path)
    assert list(tmp_path.iterdir()) == []


async def test_local_marker_retained_after_failure_blocks_second_launch(
    campaign, tmp_path, monkeypatch
):
    plan, snapshot = campaign
    identity, env = approval(plan, snapshot)
    def fail():
        raise ValueError("PRIVATE_CONSOLE_ERROR")
    monkeypatch.setattr(cli, "open_review_console", fail)
    report = await cli.execute_approved(plan, snapshot, identity, env, tmp_path)
    assert report["status"] == "stopped" and report["inference_started"] is False
    assert "PRIVATE" not in json.dumps(report)
    assert len(list(tmp_path.iterdir())) == 2
    with pytest.raises(FileExistsError):
        await cli.execute_approved(plan, snapshot, identity, env, tmp_path)


class Console(io.StringIO):
    def isatty(self):
        return True


async def test_console_review_preserves_partitions_escapes_text_no_stdout(campaign, capsys):
    case = campaign[0].validate_snapshot(campaign[1])[0]
    writer = Console()
    review = TerminalCampaignReviewer(Console("pass\npass\n"), writer)
    observed = observation(case)
    observed = EvalObservation(
        outcome=observed.outcome, reply=AgentReply(answer="\x1b[31mDATA", proposal_text="synthetic")
    )
    assert await review.review(case, observed) == ("pass", "pass")
    assert "\x1b" not in writer.getvalue()
    assert "\\u001b" in writer.getvalue()
    assert "answer (DATA)" in writer.getvalue() and "proposal_text (DATA)" in writer.getvalue()
    assert capsys.readouterr().out == ""
    with pytest.raises(ValueError, match="console_required"):
        TerminalCampaignReviewer(io.StringIO(), io.StringIO())


async def test_blank_console_input_is_not_approval(campaign):
    case = campaign[0].validate_snapshot(campaign[1])[0]
    review = TerminalCampaignReviewer(Console("\n"), Console())
    assert await review.review(case, observation(case)) == ("not_evaluated", "not_evaluated")


@pytest.mark.parametrize("text,expected", [
    ("p\nP\n", ("pass", "pass")),
    (" PASS \np\n", ("pass", "pass")),
    ("F\n", ("fail", "not_evaluated")),
    ("x\n", ("not_evaluated", "not_evaluated")),
    ("unknown\np\np\n", ("pass", "pass")),
    ("unknown\n", ("not_evaluated", "not_evaluated")),
])
async def test_console_shortcuts_and_typos_do_not_infer(campaign, text, expected):
    case = campaign[0].validate_snapshot(campaign[1])[0]
    writer = Console()
    reviewer = TerminalCampaignReviewer(Console(text), writer)
    assert await reviewer.review(case, observation(case)) == expected
    assert ("Entrada no válida" in writer.getvalue()) == text.startswith("unknown")


async def test_failure_preserved_when_later_criteria_not_evaluated(campaign):
    run, _, _ = runner(campaign, labels=["fail", "not_evaluated"])
    report = await run.run()
    assert report["results"][0]["semantic_status"] == "failed"
    assert report["status"] == "stopped"


def test_console_check_has_no_source_network_reservation_or_approval(monkeypatch, capsys):
    monkeypatch.setattr(cli, "open_review_console", lambda: (Console("p\n"), Console()))
    monkeypatch.setattr(cli, "source_identity", lambda: pytest.fail("source not needed"))
    monkeypatch.setattr(cli, "execute_approved", lambda *a: pytest.fail("no execution"))
    assert cli.main(["--check-console"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report == {
        "status": "console_ready", "inference_started": False, "approval_granted": False,
    }


def test_console_check_cannot_be_combined_with_execution(capsys):
    assert cli.main(["--check-console", "--execute"]) == 1
    assert json.loads(capsys.readouterr().out)["semantic_status"] == "not_evaluated"


async def test_remote_missing_volume_stops_before_reservation_or_network(campaign, tmp_path):
    plan, snapshot = campaign
    identity, env = approval(plan, snapshot)
    env["ANCORA_EVAL_REQUIRE_VOLUME"] = "1"
    with pytest.raises(ValueError, match="persistent_state"):
        await cli.execute_approved(plan, snapshot, identity, env, tmp_path)
    assert not list(tmp_path.iterdir())


def test_cli_default_never_needs_secrets_console_or_gateway(campaign, monkeypatch, capsys):
    monkeypatch.setattr(cli, "source_identity", lambda: {
        "code_sha": "a" * 40, "source_fingerprint": "b" * 64, "worktree": "dirty",
    })
    monkeypatch.setattr(cli, "open_review_console", lambda: pytest.fail("console in dry-run"))
    folder = ROOT / "evals" / "response_style"
    args = ["--snapshot", str(folder / "runtime-rev8-snapshot.json"),
            "--plan", str(folder / "bl48-campaign-plan.json")]
    assert cli.main(args) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["status"] == "preflight_valid"
    assert output["inference_started"] is False
    assert output["gateway_access"] == "not_checked"


async def test_gateway_scope_failure_stops_before_model(campaign, tmp_path, monkeypatch):
    plan, snapshot = campaign
    identity, env = approval(plan, snapshot)
    monkeypatch.setattr(cli, "open_review_console", lambda: (Console(), Console()))
    calls = []
    async def get(client, url, **kwargs):
        calls.append(url)
        assert client.follow_redirects is False
        return httpx.Response(200, json={"data": [{"id": "other-r1"}]})
    monkeypatch.setattr(httpx.AsyncClient, "get", get)
    monkeypatch.setattr(cli, "build_campaign_executor", lambda *a, **k: pytest.fail("scope bypass"))
    report = await cli.execute_approved(plan, snapshot, identity, env, tmp_path)
    assert report["status"] == "stopped"
    assert calls == ["http://127.0.0.1:4000/v1/models"]


async def test_full_cli_wiring_success_reuses_safe_client_and_persists_metadata_only(
    campaign, tmp_path, monkeypatch
):
    plan, snapshot = campaign
    identity, env = approval(plan, snapshot)
    monkeypatch.setattr(cli, "source_identity", lambda: identity)
    review_writer = Console()
    monkeypatch.setattr(cli, "open_review_console", lambda: (
        Console("pass\n" * 10), review_writer
    ))

    async def get(client, url, **kwargs):
        assert client.follow_redirects is False
        assert client.trust_env is False
        return httpx.Response(200, json={"data": [{"id": plan.effective_gateway_route}]})

    def build(plan, snapshot, env, recorder, *, client):
        assert client.trust_env is False and client.follow_redirects is False
        executor = AsyncMock()
        async def execute(request):
            await recorder.record(usage(plan))
            return observation(request.case)
        executor.execute.side_effect = execute
        return executor

    monkeypatch.setattr(httpx.AsyncClient, "get", get)
    monkeypatch.setattr(cli, "build_campaign_executor", build)
    report = await cli.execute_approved(plan, snapshot, identity, env, tmp_path)
    assert report["status"] == "passed"
    persisted = (tmp_path / (plan.checksum() + ".report.json")).read_text()
    assert "PRIVATE_SYNTHETIC" not in persisted
    assert "PRIVATE_KEY" not in persisted
    assert json.loads(persisted)["recorded_model_calls"] == 5


def test_cli_live_output_suppresses_library_text_and_restores_logging(
    campaign, monkeypatch, capsys
):
    import logging
    import sys
    identity, _ = approval(*campaign)
    monkeypatch.setattr(cli, "source_identity", lambda: identity)
    async def execute(*args, **kwargs):
        print("PRIVATE_PROVIDER_OUTPUT")
        print("PRIVATE_PROVIDER_ERROR", file=sys.stderr)
        logging.error("PRIVATE_LOG")
        return {"status": "passed", "semantic_status": "passed"}
    monkeypatch.setattr(cli, "execute_approved", execute)
    folder = ROOT / "evals" / "response_style"
    args = ["--snapshot", str(folder / "runtime-rev8-snapshot.json"),
            "--plan", str(folder / "bl48-campaign-plan.json"), "--execute"]
    previous = logging.root.manager.disable
    assert cli.main(args) == 0
    output = capsys.readouterr()
    assert "PRIVATE" not in output.out + output.err
    assert logging.root.manager.disable == previous

