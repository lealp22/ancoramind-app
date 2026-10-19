"""One-shot isolated evals. Default is pure preflight; --execute requires approval."""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import logging
import os
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Any, TextIO

import httpx

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.eval_source import source_identity as read_source_identity  # noqa: E402
from src.agent.eval_campaign import (  # noqa: E402
    EvalCampaignPlan,
    EvalUsageRecorder,
    build_campaign_executor,
    gateway_settings,
    verify_gateway_models,
)
from src.agent.eval_campaign_runner import (  # noqa: E402
    EvalCampaignRunner,
    TerminalCampaignReviewer,
    campaign_cases_fingerprint,
)
from src.domain.runtime_config.models import RuntimeConfigSnapshot  # noqa: E402

if TYPE_CHECKING:
    from src.agent.eval_validation_session import EvalValidationSession


def source_identity(root: Path = ROOT) -> dict[str, str]:
    return read_source_identity(root)


def validate_live_approval(
    plan: EvalCampaignPlan, identity: Mapping[str, str], cases_fingerprint: str,
    env: Mapping[str, str],
) -> None:
    expected = {
        "ANCORA_EVAL_APPROVED_PLAN": plan.checksum(),
        "ANCORA_EVAL_APPROVED_SHA": identity["code_sha"],
        "ANCORA_EVAL_APPROVED_SOURCE": identity["source_fingerprint"],
        "ANCORA_EVAL_APPROVED_CASES": cases_fingerprint,
        "ANCORA_EVAL_SYNTHETIC_APPROVED": "1",
        "ANCORA_EVAL_EXTERNAL_BUDGET_VERIFIED": "1",
        "ANCORA_EVAL_SNAPSHOT_PROVENANCE_ACCEPTED": "1",
        "ANCORA_EVAL_HUMAN_REVIEW_APPROVED": "1",
    }
    if identity["worktree"] != "clean" or any(env.get(k) != v for k, v in expected.items()):
        raise ValueError("eval_live_approval_or_clean_commit_required")


def open_review_console() -> tuple[TextIO, TextIO]:
    """Never fall back to redirected stdin/stdout for reviewing synthetic content."""
    reader = open(  # noqa: SIM115 - ownership transferred to caller's context manager
        "CONIN$" if os.name == "nt" else "/dev/tty", encoding="utf-8"
    )
    try:
        writer = open(  # noqa: SIM115 - ownership transferred to caller's context manager
            "CONOUT$" if os.name == "nt" else "/dev/tty", "w", encoding="utf-8"
        )
    except BaseException:
        reader.close()
        raise
    return reader, writer


def validate_state_directory(
    state_dir: Path, env: Mapping[str, str], *, sealed_image: bool = False,
) -> None:
    """Remote evals require an actual mounted directory, not ephemeral storage."""
    if (
        not state_dir.is_absolute()
        or any(path.is_symlink() for path in (state_dir, *state_dir.parents))
        or (sealed_image and state_dir != Path("/eval-state"))
        or ((sealed_image or env.get("ANCORA_EVAL_REQUIRE_VOLUME") == "1")
            and (state_dir == Path(state_dir.anchor) or not state_dir.is_mount()))
    ):
        raise ValueError("eval_persistent_state_directory_required")


async def check_console() -> dict[str, object]:
    """Exercise the same human reviewer without model, key, approval or reservation."""
    from src.agent.evals import EvalCase, EvalObservation
    from src.domain.interactions.reply import AgentReply

    case = EvalCase(
        case_id="console_check.synthetic", category="console_check",
        input_text="Comprobar teclado sin llamar al modelo.", synthetic_context={},
        expected_outcome="safe_response", required_tool=None, forbidden_tools=frozenset(),
        requires_user_confirmation=False,
        response_criteria=("La respuesta indica que no se ha llamado al modelo.",),
    )
    reader, writer = open_review_console()
    with reader, writer:
        labels = await TerminalCampaignReviewer(reader, writer).review(
            case, EvalObservation(outcome="safe_response", reply=AgentReply(
                answer="Prueba de consola: no se ha llamado al modelo.", proposal_text="",
            )),
        )
    return {"status": "console_ready" if labels == ("pass",) else "console_stopped",
            "inference_started": False, "approval_granted": False}


async def execute_approved(
    plan: EvalCampaignPlan, snapshot: RuntimeConfigSnapshot, identity: dict[str, str],
    env: Mapping[str, str], state_dir: Path, *, durable: tuple[Any, str] | None = None,
    validation_session: EvalValidationSession | None = None,
) -> dict[str, object]:
    """Reserve durable local one-shot marker before network/inference; never resume."""
    cases = plan.validate_snapshot(snapshot)
    if validation_session is not None and durable is None:
        raise ValueError("eval_session_requires_durable_evidence")
    case_hash = campaign_cases_fingerprint(cases)
    validate_live_approval(plan, identity, case_hash, env)
    settings = gateway_settings(env)
    validate_state_directory(
        state_dir, env, sealed_image=identity.get("identity_source") == "sealed_image",
    )
    # Settings validation does not perform I/O. Check private access only after
    # approval and local anti-replay reservation; unknown result consumes the run.
    state_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    if state_dir.is_symlink():
        raise ValueError("eval_state_directory_invalid")
    tag = plan.checksum()
    if durable is not None:
        # New candidate with explicit new SHA approval, never a replay of an old run.
        tag += "." + identity["source_fingerprint"]
    marker = state_dir / (tag + ".reserved.json")
    report_path = state_dir / (tag + ".report.json")
    reservation = {
        **identity, "plan_checksum": plan.checksum(), "cases_fingerprint": case_hash,
        "reserved_estimated_cost_usd": ("0" if validation_session else
                                        str(plan.total_estimated_cost_usd)),
        "reservation_mode": "per_case_session" if validation_session else "whole_campaign",
        "status": "consumed_do_not_replay",
    }
    # Atomic exclusive creation protects simultaneous launches on this machine.
    with marker.open("x", encoding="utf-8") as file:
        json.dump(reservation, file)
        file.flush()
        os.fsync(file.fileno())
    with report_path.open("x+", encoding="utf-8") as report_file:
        def checkpoint(report: dict[str, object]) -> None:
            report_file.seek(0)
            json.dump(report, report_file, ensure_ascii=True, allow_nan=False)
            report_file.truncate()
            report_file.flush()
            os.fsync(report_file.fileno())
            if durable is not None:
                durable[0].append(durable[1], "checkpoint", report)

        initial = {**reservation, "status": "reserved", "inference_started": False,
                   "semantic_status": "not_evaluated"}
        checkpoint(initial)
        runner: EvalCampaignRunner | None = None
        try:
            with contextlib.ExitStack() as stack:
                if durable is None:
                    reader, writer = open_review_console()
                    stack.enter_context(reader)
                    stack.enter_context(writer)
                    reviewer: Any = TerminalCampaignReviewer(reader, writer)
                else:
                    from src.agent.eval_durable_review import DurableCampaignReviewer
                    reviewer = DurableCampaignReviewer(durable[0], durable[1])
                async with httpx.AsyncClient(
                    timeout=snapshot.config.gateway.request_timeout_seconds,
                    follow_redirects=False, trust_env=False,
                ) as client:
                    async def session_check() -> None:
                        if validation_session is not None:
                            from src.agent.eval_validation_session import read_session_gateway

                            await read_session_gateway(
                                client, settings.litellm_proxy_base_url.rstrip("/"),
                                settings.litellm_proxy_virtual_key, plan, validation_session,
                            )

                    async def before_request(request: httpx.Request) -> None:
                        if request.method == "POST" and validation_session is not None:
                            try:
                                await session_check()
                                await validation_session.before_request(request)
                            except Exception as error:
                                from src.agent.eval_validation_session import (
                                    EvalSessionError,
                                    session_reason,
                                )

                                validation_session.blocked_reason = (
                                    session_reason(str(error))
                                    if isinstance(error, EvalSessionError)
                                    else "session_budget_unverifiable"
                                )
                                raise

                    if validation_session is not None:
                        async def after_response(response: httpx.Response) -> None:
                            if response.request.method == "POST":
                                try:
                                    await session_check()
                                except Exception:
                                    validation_session.blocked_reason = (
                                        "session_budget_unverifiable"
                                    )
                                    raise

                        client.event_hooks["request"].append(before_request)
                        client.event_hooks["response"].append(after_response)
                    response = await client.get(
                        settings.litellm_proxy_base_url.rstrip("/") + "/models",
                        headers={"Authorization": "Bearer " + settings.litellm_proxy_virtual_key},
                    )
                    if response.status_code != 200:
                        raise ValueError("eval_gateway_auth_failed")
                    verify_gateway_models(response.json(), plan.effective_gateway_route)
                    recorder = EvalUsageRecorder()
                    executor = build_campaign_executor(plan, snapshot, env, recorder, client=client)
                    runner = EvalCampaignRunner(
                        plan=plan, snapshot=snapshot, executor=executor, recorder=recorder,
                        reviewer=reviewer, code_sha=identity["code_sha"],
                    )
                    runner.report.update(identity)
                    if validation_session is not None:
                        runner.report.update(reservation_mode="per_case_session",
                                             reserved_estimated_cost_usd="0")

                    async def unchanged() -> None:
                        if source_identity() != identity:
                            raise ValueError("eval_sources_changed")

                    async def reserve_case(case_id: str) -> None:
                        if validation_session is not None:
                            from decimal import Decimal

                            await session_check()
                            validation_session.reserve(
                                durable[1], case_id, identity["source_fingerprint"],
                                Decimal(str(plan.budget.max_estimated_cost_usd)),
                            )

                    if validation_session is None:
                        return await runner.run(checkpoint=checkpoint, before_case=unchanged)
                    report = await runner.run(
                        checkpoint=checkpoint, before_case=unchanged, case_started=reserve_case,
                        case_finished=lambda events, passed: validation_session.settle(
                            events, passed=passed,
                        ),
                    )
                    if validation_session.blocked_reason:
                        results = report.get("results", [])
                        if isinstance(results, list):
                            for item in results:
                                if item.get("status") == "stopped":
                                    item["session_reason"] = validation_session.blocked_reason
                        checkpoint(report)
                    return report
        except (Exception, asyncio.CancelledError) as error:
            partial = runner.report if runner is not None else initial
            partial.update(status="stopped", error_class=type(error).__name__)
            partial.setdefault("semantic_status", "not_evaluated")
            checkpoint(partial)
            return partial


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path)
    parser.add_argument("--plan", type=Path)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--state-dir", type=Path)
    parser.add_argument("--check-console", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.check_console:
            if args.execute or args.snapshot or args.plan or args.state_dir:
                raise ValueError("eval_console_check_is_separate")
            result = asyncio.run(check_console())
            print(json.dumps(result))
            return 0 if result["status"] == "console_ready" else 1
        if args.snapshot is None or args.plan is None:
            raise ValueError("eval_snapshot_and_plan_required")
        if not args.snapshot.is_absolute() or not args.plan.is_absolute():
            raise ValueError("eval_absolute_paths_required")
        snapshot = RuntimeConfigSnapshot.model_validate_json(
            args.snapshot.read_text(encoding="utf-8")
        )
        plan = EvalCampaignPlan.model_validate_json(args.plan.read_text(encoding="utf-8"))
        cases = plan.validate_snapshot(snapshot)
        identity = source_identity()
        metadata = {
            **plan.metadata(), **identity, "cases_fingerprint": campaign_cases_fingerprint(cases),
            "status": "preflight_valid", "inference_started": False,
            "approval_status": "pending_separate_approval", "gateway_access": "not_checked",
        }
        if not args.execute:
            print(json.dumps(metadata))
            return 0
        # SDK/Agno may log prompt/result or errors. Suppress all such output for
        # the live command; a separately opened console handles human review.
        disabled = logging.root.manager.disable
        try:
            logging.disable(sys.maxsize)
            with (
                open(os.devnull, "w") as sink,
                contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink),
            ):
                report = asyncio.run(execute_approved(
                    plan, snapshot, identity, dict(os.environ),
                    args.state_dir or Path(os.environ.get(
                        "ANCORA_EVAL_STATE_DIR", str(ROOT / "tmp" / "eval-campaigns")
                    )),
                ))
        finally:
            logging.disable(disabled)
        print(json.dumps(report, ensure_ascii=True, allow_nan=False))
        return 0 if report["status"] == "passed" else 1
    except (Exception, KeyboardInterrupt):
        print(json.dumps({"status": "blocked_or_stopped", "semantic_status": "not_evaluated"}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
