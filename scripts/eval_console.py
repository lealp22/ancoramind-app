"""Reusable eval console: explicit run, reconnectable review, curated golden export.

Configure secrets once in the PRIVATE eval service environment; no CLI key args.
run launches one detached worker; review/status/label/promote/export never infer.
No startup evaluation, web server, new DB, judge or automatic replay/restart.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import logging
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.execute_eval_campaign import (  # noqa: E402
    execute_approved,
    open_review_console,
    source_identity,
    validate_live_approval,
    validate_state_directory,
)
from src.agent.eval_campaign import EvalCampaignPlan, gateway_settings  # noqa: E402
from src.agent.eval_campaign_runner import campaign_cases_fingerprint  # noqa: E402
from src.agent.eval_durable_review import case_record, review_saved  # noqa: E402
from src.agent.eval_evidence import EvalEvidenceStore  # noqa: E402
from src.domain.runtime_config.models import RuntimeConfigSnapshot  # noqa: E402


def store_from_env(env: dict[str, str]) -> tuple[EvalEvidenceStore, Path]:
    state = Path(env.get("ANCORA_EVAL_STATE_DIR", "/eval-state"))
    validate_state_directory(state, env)
    key = env.get("ANCORA_EVAL_EVIDENCE_KEY", "")
    if not key:
        raise ValueError("eval_evidence_encryption_key_required")
    return EvalEvidenceStore(state / "private-evidence", key), state


def prepare(store: EvalEvidenceStore, state: Path, approval_path: Path) -> str:
    if not approval_path.is_absolute() or approval_path.is_symlink():
        raise ValueError("eval_approval_absolute_file_required")
    approval = json.loads(approval_path.read_text(encoding="utf-8"))
    if approval.get("evidence_synthetic_approved") is not True:
        raise ValueError("eval_synthetic_persistence_not_approved")
    identity = source_identity()
    validate_state_directory(state, dict(os.environ),
                             sealed_image=identity.get("identity_source") == "sealed_image")
    folder = ROOT / "evals" / "response_style"
    snapshot = RuntimeConfigSnapshot.model_validate_json(
        (folder / "runtime-rev8-snapshot.json").read_text(encoding="utf-8")
    )
    plan = EvalCampaignPlan.model_validate_json(
        (folder / "bl48-campaign-plan.json").read_text(encoding="utf-8")
    )
    cases = plan.validate_snapshot(snapshot)
    gateway_settings(dict(os.environ))  # fail before launch if reusable access is missing
    expected_gate_names = {
        "ANCORA_EVAL_APPROVED_PLAN", "ANCORA_EVAL_APPROVED_SHA", "ANCORA_EVAL_APPROVED_SOURCE",
        "ANCORA_EVAL_APPROVED_CASES", "ANCORA_EVAL_SYNTHETIC_APPROVED",
        "ANCORA_EVAL_EXTERNAL_BUDGET_VERIFIED", "ANCORA_EVAL_SNAPSHOT_PROVENANCE_ACCEPTED",
        "ANCORA_EVAL_HUMAN_REVIEW_APPROVED",
    }
    if set(approval["gates"]) != expected_gate_names:
        raise ValueError("eval_approval_file_must_not_contain_credentials")
    gates = approval["gates"]
    validate_live_approval(plan, identity, campaign_cases_fingerprint(cases), gates)
    # Original interrupted one-shot remains consumed; never silently migrate/replay it.
    legacy = state / (plan.checksum() + ".reserved.json")
    if legacy.exists():
        old = json.loads(legacy.read_text(encoding="utf-8"))
        if old.get("source_fingerprint") in {None, identity["source_fingerprint"]}:
            raise ValueError("eval_plan_consumed_requires_new_explicit_candidate")
    run_id = store.create(identity, plan.model_dump(mode="json"),
                          [case_record(case) for case in cases],
                          snapshot.model_dump(mode="json", by_alias=True), synthetic_approved=True)
    store.append(run_id, "approval", {"gates": gates})
    return run_id


async def validate_reusable_access(plan: EvalCampaignPlan, env: dict[str, str]) -> None:
    """Read existing dedicated key before inference; no create/reset/extend/rotate."""
    from datetime import UTC, datetime
    from decimal import Decimal

    import httpx

    from src.agent.eval_campaign import gateway_settings, verify_gateway_models

    settings = gateway_settings(env)
    base = settings.litellm_proxy_base_url.rstrip("/")
    async with httpx.AsyncClient(timeout=15, follow_redirects=False, trust_env=False) as client:
        headers = {"Authorization": "Bearer " + settings.litellm_proxy_virtual_key}
        response = await client.get(base.removesuffix("/v1") + "/key/info", headers=headers)
        response.raise_for_status()
        info = response.json()["info"]
        expires = datetime.fromisoformat(info["expires"].replace("Z", "+00:00"))
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=UTC)
        spend, ceiling = Decimal(str(info["spend"])), Decimal(str(info["max_budget"]))
        allowed = {"/models", "/v1/models", "/key/info", "/chat/completions",
                   "/v1/chat/completions"}
        if (info.get("models") != [plan.effective_gateway_route]
            or not str(info.get("key_alias", "")).startswith("ancoramind-evals-")
            or not spend.is_finite() or not ceiling.is_finite() or spend < 0
            or ceiling <= 0 or ceiling > 1 or ceiling - spend < plan.total_estimated_cost_usd
            or info.get("max_parallel_requests") != 1 or info.get("budget_duration") is not None
            or info.get("blocked") or not datetime.now(UTC) < expires
            or not set(info.get("allowed_routes") or []) <= allowed
            or not {"/v1/chat/completions", "/key/info"} <= set(info.get("allowed_routes") or [])):
            raise ValueError("eval_reusable_key_scope_budget_or_expiry_invalid")
        for name in ("aliases", "config", "permissions"):
            value = info.get(name)
            if isinstance(value, str):
                value = json.loads(value)
            if value is not None and value != {}:
                raise ValueError("eval_reusable_key_overrides_forbidden")
        response = await client.get(base + "/models", headers=headers)
        response.raise_for_status()
        verify_gateway_models(response.json(), plan.effective_gateway_route)


async def work(store: EvalEvidenceStore, state: Path, run_id: str, env: dict[str, str]) -> None:
    manifest = store.manifest(run_id)
    if source_identity() != manifest["identity"]:
        raise ValueError("eval_worker_identity_changed")
    events = store.events(run_id)
    if any(event["kind"] == "worker_started" for event in events):
        raise ValueError("eval_worker_already_consumed_no_restart")
    store.append(run_id, "worker_started", {"pid": os.getpid()})
    approval = next(event["data"]["gates"] for event in events if event["kind"] == "approval")
    plan = EvalCampaignPlan.model_validate(manifest["plan"])
    snapshot = RuntimeConfigSnapshot.model_validate(manifest["snapshot"])
    gated_env = {**env, **approval}
    try:
        await validate_reusable_access(plan, gated_env)
        await execute_approved(plan, snapshot, manifest["identity"], gated_env, state,
                               durable=(store, run_id))
    except (Exception, asyncio.CancelledError):
        store.append(run_id, "worker_failed", {"status": "uncertain_do_not_restart"})


def start_worker(run_id: str) -> int:
    # No secrets in args/stdout/stderr. Environment already configured by the operator.
    options = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
               } if os.name == "nt" else {"start_new_session": True}
    process = subprocess.Popen(
        [sys.executable, str(Path(__file__).resolve()), "worker", "--run", run_id],
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        **options,
    )
    return process.pid


async def review_loop(store: EvalEvidenceStore, run_id: str, reviewer: str) -> dict:
    # Terminal held only by review process. SSH loss does not affect detached worker.
    reader, writer = open_review_console()
    with reader, writer:
        while True:
            await review_saved(store, run_id, reviewer, reader, writer)
            status = store.status(run_id)
            labels = [label["label"] for case in status["cases"] for label in case["criteria"]]
            if any(label != "pass" for label in labels):
                return status
            if status["execution_status"] in {"passed", "stopped", "uncertain_do_not_restart"}:
                return status
            if status["execution_status"] == "not_started" and not any(
                e["kind"] == "worker_started" for e in store.events(run_id)
            ):
                manifest = store.manifest(run_id)
                from datetime import datetime
                if time.time() - datetime.fromisoformat(manifest["created_at"]).timestamp() > 30:
                    return {**status, "execution_status": "worker_not_started_do_not_replay"}
            await asyncio.sleep(1)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("command", choices=["run", "worker", "review", "status", "list", "label",
                                            "promote", "export", "purge"])
    result.add_argument("--run", dest="run_id")
    result.add_argument("--reviewer", default="owner")
    result.add_argument("--case")
    result.add_argument("--criterion", type=int)
    result.add_argument("--label", choices=["pass", "fail", "not_evaluated"])
    result.add_argument("--comment", default="")
    result.add_argument("--dataset", choices=["agent", "judge"])
    result.add_argument("--split", choices=["development", "validation"])
    result.add_argument("--sanitized-approved", action="store_true")
    result.add_argument("--version")
    result.add_argument("--output", type=Path)
    result.add_argument("--approval", type=Path)
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    disabled = logging.root.manager.disable
    try:
        logging.disable(sys.maxsize)
        store, state = store_from_env(dict(os.environ))
        if args.command == "run":
            reader, writer = open_review_console()
            with reader, writer:
                if not reader.isatty() or not writer.isatty():
                    raise ValueError("eval_initial_human_console_required")
            approval = args.approval or Path(os.environ.get(
                "ANCORA_EVAL_APPROVAL_FILE", str(state / "approval.json"),
            ))
            run_id = prepare(store, state, approval)
            start_worker(run_id)
            print(json.dumps({"run_id": run_id, "status": "worker_launched",
                              "reconnect": "review --run " + run_id}), flush=True)
            report = asyncio.run(review_loop(store, run_id, args.reviewer))
        elif args.command == "worker":
            with open(os.devnull, "w") as sink, contextlib.redirect_stdout(sink), \
                    contextlib.redirect_stderr(sink):
                asyncio.run(work(store, state, args.run_id, dict(os.environ)))
            return 0
        elif args.command == "review":
            report = asyncio.run(review_loop(store, args.run_id, args.reviewer))
        elif args.command == "status":
            report = store.status(args.run_id)
        elif args.command == "list":
            report = {"runs": store.runs()}
        elif args.command == "label":
            store.review(args.run_id, args.case, args.criterion, args.label,
                         args.reviewer, args.comment)
            report = store.status(args.run_id)
        elif args.command == "promote":
            version = store.promote(args.run_id, args.case, dataset=args.dataset,
                                    reviewer=args.reviewer, split=args.split,
                                    sanitized_approved=args.sanitized_approved)
            report = {"status": "golden_promoted", "version": version, "dataset": args.dataset}
        elif args.command == "export":
            store.export(args.version, args.output, sanitized_approved=args.sanitized_approved)
            report = {"status": "golden_exported"}
        else:
            store.purge(args.run_id)
            report = {"status": "content_purged_markers_retained"}
        print(json.dumps(report, ensure_ascii=True, allow_nan=False))
        return 0
    except (Exception, KeyboardInterrupt):
        print(json.dumps({"status": "eval_console_blocked_or_disconnected",
                          "do_not_replay": True, "review_can_reopen_saved_evidence": True}))
        return 1
    finally:
        logging.disable(disabled)


if __name__ == "__main__":
    raise SystemExit(main())
