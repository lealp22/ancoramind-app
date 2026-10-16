"""One-shot isolated evals. Default is pure preflight; --execute requires approval."""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import hashlib
import json
import logging
import os
import shutil
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import TextIO

import httpx

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

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


def source_identity(root: Path = ROOT) -> dict[str, str]:
    """Read local code identity without logging git output or loading credentials."""
    git = shutil.which("git")
    if git is None:
        raise ValueError("eval_git_required")
    sha = subprocess.run(  # noqa: S603 - fixed git subcommand, no shell/user arguments
        [git, "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True,
        timeout=10, check=True,
    ).stdout.strip()
    dirty = subprocess.run(  # noqa: S603 - fixed git subcommand, no shell/user arguments
        [git, "status", "--porcelain"], cwd=root, capture_output=True, text=True,
        timeout=10, check=True,
    ).stdout.strip()
    digest = hashlib.sha256()
    for folder, pattern in (("src", "*.py"), ("scripts", "*.py"),
                            ("prompts", "*.md"), ("evals", "*.json")):
        for path in sorted((root / folder).rglob(pattern)):
            digest.update(path.relative_to(root).as_posix().encode())
            digest.update(b"\0")
            # Stable across Git autocrlf checkout, but not changes of content.
            digest.update(path.read_text(encoding="utf-8").replace("\r\n", "\n").encode())
            digest.update(b"\0")
    return {"code_sha": sha, "source_fingerprint": digest.hexdigest(),
            "worktree": "dirty" if dirty else "clean"}


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


async def execute_approved(
    plan: EvalCampaignPlan, snapshot: RuntimeConfigSnapshot, identity: dict[str, str],
    env: Mapping[str, str], state_dir: Path,
) -> dict[str, object]:
    """Reserve durable local one-shot marker before network/inference; never resume."""
    cases = plan.validate_snapshot(snapshot)
    case_hash = campaign_cases_fingerprint(cases)
    validate_live_approval(plan, identity, case_hash, env)
    settings = gateway_settings(env)
    # Settings validation does not perform I/O. Check private access only after
    # approval and local anti-replay reservation; unknown result consumes the run.
    state_dir.mkdir(parents=True, exist_ok=True)
    if state_dir.is_symlink():
        raise ValueError("eval_state_directory_invalid")
    marker = state_dir / (plan.checksum() + ".reserved.json")
    report_path = state_dir / (plan.checksum() + ".report.json")
    reservation = {
        **identity, "plan_checksum": plan.checksum(), "cases_fingerprint": case_hash,
        "reserved_estimated_cost_usd": str(plan.total_estimated_cost_usd),
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

        initial = {**reservation, "status": "reserved", "inference_started": False,
                   "semantic_status": "not_evaluated"}
        checkpoint(initial)
        runner: EvalCampaignRunner | None = None
        try:
            reader, writer = open_review_console()
            with reader, writer:
                reviewer = TerminalCampaignReviewer(reader, writer)
                async with httpx.AsyncClient(
                    timeout=snapshot.config.gateway.request_timeout_seconds,
                    follow_redirects=False, trust_env=False,
                ) as client:
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

                    async def unchanged() -> None:
                        if source_identity() != identity:
                            raise ValueError("eval_sources_changed")

                    return await runner.run(checkpoint=checkpoint, before_case=unchanged)
        except (Exception, asyncio.CancelledError) as error:
            partial = runner.report if runner is not None else initial
            partial.update(status="stopped", error_class=type(error).__name__)
            partial.setdefault("semantic_status", "not_evaluated")
            checkpoint(partial)
            return partial


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args(argv)
    try:
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
                    plan, snapshot, identity, dict(os.environ), ROOT / "tmp" / "eval-campaigns"
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
