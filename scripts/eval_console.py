"""Reusable eval console: explicit run, reconnectable review, curated golden export.

Configure secrets once in the PRIVATE eval service environment; no CLI key args.
run launches one detached worker; review/status/label/promote/export never infer.
No startup evaluation, web server, new DB, judge or automatic replay/restart.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import hashlib
import json
import logging
import os
import subprocess
import sys
import time
from decimal import ROUND_DOWN, Decimal
from pathlib import Path
from typing import Any

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
from src.agent.eval_campaign_runner import (  # noqa: E402
    _escape,
    campaign_cases_fingerprint,
)
from src.agent.eval_durable_review import case_record, review_saved  # noqa: E402
from src.agent.eval_evidence import EvalEvidenceStore  # noqa: E402
from src.agent.eval_validation_session import (  # noqa: E402
    EvalSessionError,
    EvalValidationSession,
    read_session_gateway,
    session_reason,
    session_scope,
)
from src.domain.runtime_config.models import RuntimeConfigSnapshot  # noqa: E402

# Historical campaign used separate short-lived keys before the reusable key
# and current cumulative authorization. Preserve it; never charge it a second time.
PRE_SESSION_SHA = "db0c59be0b2eeb807d4222aeb5a62b622d90b200"

# Closed reasons for eval_console_blocked_or_disconnected (specs/045 C). Keys are the
# fixed internal error codes; exception text is never echoed, only looked up.
_CONSOLE_REASONS: dict[str, str] = {
    "eval_initial_human_console_required": "console_not_interactive",
    "eval_human_console_required": "console_not_interactive",
    "eval_review_disconnected_no_label_saved": "review_disconnected",
    "eval_review_wait_expired": "review_disconnected",
    "eval_evidence_encryption_key_required": "evidence_unreadable_or_wrong_key",
    "eval_evidence_corrupted_or_wrong_key": "evidence_unreadable_or_wrong_key",
    "eval_evidence_corrupted": "evidence_unreadable_or_wrong_key",
    "eval_evidence_sequence_corrupted": "evidence_unreadable_or_wrong_key",
    "eval_evidence_chain_corrupted": "evidence_unreadable_or_wrong_key",
    "eval_evidence_missing_head": "evidence_unreadable_or_wrong_key",
    "eval_evidence_invalid_run": "run_not_found",
    "eval_evidence_unknown_case": "run_not_found",
}


# Fixed next-step table for `--human` (specs/045 D). No entry tells the operator to
# launch a new run to reconnect or retry: a consumed case is never replayed.
_NEXT_STEP: dict[str, str] = {
    "not_started": "Aún no hay worker. Espera unos segundos y consulta `status` de nuevo; "
                   "no relances la campaña.",
    "reserved": "El worker está arrancando. Consulta `status` de nuevo en unos segundos.",
    "running": "El worker sigue en marcha. Abre `review --run ID` para etiquetar lo capturado.",
    "passed": "Campaña completada. Usa `review --run ID` si quedan criterios sin etiquetar "
              "y después `promote` si procede.",
    "stopped": "Campaña detenida. Usa `review --run ID` para etiquetar lo capturado; "
               "un caso consumido no se repite.",
    "uncertain_do_not_restart": "Estado incierto. No relances nada: pide inspección antes "
                                "de cualquier otra acción.",
}
_NEXT_STEP_UNKNOWN = "Sin acción sugerida para este estado."


def _human_count(value: object) -> str:
    return str(value) if type(value) is int else "?"


def human_status(status: dict[str, Any], totals: dict[str, int] | None = None) -> str:
    """Plain-text run summary. Every value is escaped; no content beyond status fields."""
    totals = totals or {}
    state = str(status.get("execution_status"))
    lines = [
        f"Run {_escape(str(status.get('run_id')))}",
        f"Estado: {_escape(state)}",
        f"Inferencia iniciada: {'sí' if status.get('inference_started') else 'no'}",
        f"Llamadas al modelo registradas: {_human_count(status.get('recorded_model_calls'))}",
        "Casos:",
    ]
    for case in status.get("cases", []):
        case_id = str(case.get("case_id"))
        labelled = len(case.get("criteria", []))
        total = totals.get(case_id)
        lines.append(
            f"  - {_escape(case_id)}: técnico={_escape(str(case.get('execution_status')))}"
            f" semántico={_escape(str(case.get('semantic_status')))}"
            f" criterios={labelled}/{'?' if total is None else total}"
        )
    lines.append("Siguiente paso: " + _NEXT_STEP.get(state, _NEXT_STEP_UNKNOWN))
    return "\n".join(lines)


def human_session(summary: dict[str, Any]) -> str:
    """Plain-text session balance. Reservations are conservative, not an invoice."""
    attempts = summary.get("attempts", [])
    lines = [
        "Sesión de validación",
        f"Límite: {_escape(str(summary.get('limit_usd')))} USD (reservas conservadoras, "
        "no factura)",
        f"Cargado o reservado: {_escape(str(summary.get('charged_or_reserved_usd')))} USD",
        f"Disponible: {_escape(str(summary.get('available_usd')))} USD",
        f"Intentos registrados: {len(attempts)}",
    ]
    lines.extend(
        f"  - {_escape(str(item.get('case_id')))}: {_escape(str(item.get('status')))}"
        f" ({_escape(str(item.get('charged')))} USD)" for item in attempts
    )
    lines.append("Siguiente paso: lanzar casos nuevos es una decisión del propietario; "
                 "un caso ya consumido no se repite.")
    return "\n".join(lines)


def console_failure_reason(error: BaseException) -> str:
    """Map an exception to a closed reason; anything unrecognised is `unexpected`."""
    if isinstance(error, KeyboardInterrupt | EOFError):
        return "review_disconnected"
    if isinstance(error, FileNotFoundError):
        return "run_not_found"
    if isinstance(error, ValueError | TimeoutError):
        return _CONSOLE_REASONS.get(str(error), "unexpected")
    return "unexpected"


def store_from_env(env: dict[str, str]) -> tuple[EvalEvidenceStore, Path]:
    state = Path(env.get("ANCORA_EVAL_STATE_DIR", "/eval-state"))
    validate_state_directory(state, env)
    key = env.get("ANCORA_EVAL_EVIDENCE_KEY", "")
    if not key:
        raise ValueError("eval_evidence_encryption_key_required")
    return EvalEvidenceStore(state / "private-evidence", key), state


def campaign_config() -> tuple[EvalCampaignPlan, RuntimeConfigSnapshot]:
    folder = ROOT / "evals" / "response_style"
    snapshot = RuntimeConfigSnapshot.model_validate_json(
        (folder / "runtime-rev8-snapshot.json").read_text(encoding="utf-8"),
    )
    plan = EvalCampaignPlan.model_validate_json(
        (folder / "bl48-campaign-plan.json").read_text(encoding="utf-8"),
    )
    plan.validate_snapshot(snapshot)
    return plan, snapshot


async def check_session_access(session: EvalValidationSession, plan: EvalCampaignPlan,
                               env: dict[str, str]) -> dict[str, Any]:
    import httpx

    settings = gateway_settings(env)
    async with httpx.AsyncClient(timeout=15, follow_redirects=False, trust_env=False) as client:
        await read_session_gateway(client, settings.litellm_proxy_base_url.rstrip("/"),
                                   settings.litellm_proxy_virtual_key, plan, session)
    return session.summary()


def approval_gates(plan: EvalCampaignPlan, snapshot: RuntimeConfigSnapshot,
                   identity: dict[str, str]) -> dict[str, str]:
    return {
        "ANCORA_EVAL_APPROVED_PLAN": plan.checksum(),
        "ANCORA_EVAL_APPROVED_SHA": identity["code_sha"],
        "ANCORA_EVAL_APPROVED_SOURCE": identity["source_fingerprint"],
        "ANCORA_EVAL_APPROVED_CASES": campaign_cases_fingerprint(plan.validate_snapshot(snapshot)),
        "ANCORA_EVAL_SYNTHETIC_APPROVED": "1", "ANCORA_EVAL_EXTERNAL_BUDGET_VERIFIED": "1",
        "ANCORA_EVAL_SNAPSHOT_PROVENANCE_ACCEPTED": "1", "ANCORA_EVAL_HUMAN_REVIEW_APPROVED": "1",
    }


def session_history(state: Path, plan: EvalCampaignPlan) -> list[dict[str, Any]]:
    history = []
    reports = sorted(state.glob(plan.checksum() + "*.report.json"))
    for marker in state.glob(plan.checksum() + "*.reserved.json"):
        report = marker.with_name(marker.name.removesuffix(".reserved.json") + ".report.json")
        if marker.is_symlink() or report not in reports:
            raise EvalSessionError("session_history_unverifiable")
    for path in reports:
        if path.is_symlink() or path.stat().st_size > 2_000_000:
            raise EvalSessionError("session_history_unverifiable")
        report = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(report, dict):
            raise EvalSessionError("session_history_unverifiable")
        # Separate the explicitly excluded, pre-session candidate first. Its
        # interrupted checkpoint is not evidence of a running reusable-key job.
        # Preserve every file/marker; this grants no replay of that historical run.
        if report.get("code_sha") == PRE_SESSION_SHA:
            continue
        if report.get("status") not in {"stopped", "passed"}:
            raise EvalSessionError("session_prior_execution_not_terminal")
        if (report.get("plan_checksum") != plan.checksum()
            or report.get("cases_fingerprint") != campaign_cases_fingerprint(
                plan.validate_snapshot(campaign_config()[1]),
            )):
            raise EvalSessionError("session_history_unverifiable")
        usage = report.get("usage", [])
        history.append({
            "run_id": "legacy:" + hashlib.sha256(path.name.encode()).hexdigest(),
            "source": report["source_fingerprint"], "results": report["results"],
            # A provider-side error event is bounded by the case reservation that
            # is already charged; any other error class (timeout, network, ...)
            # stays uncertain.
            "usage_complete": (len(usage) == report.get("recorded_model_calls")
                               and all(item.get("status") == "completed"
                                       or (item.get("status") == "error"
                                           and item.get("error_class") == "ModelProviderError")
                                       for item in usage)),
        })
    return history


def verify_imported_runs(store: EvalEvidenceStore, history: list[dict[str, Any]]) -> None:
    imported = {run["source"] for run in history}
    for folder in store.root.iterdir():
        if len(folder.name) != 32 or not all(c in "0123456789abcdef" for c in folder.name):
            continue
        manifest = store.manifest(folder.name, allow_expired=True)
        if manifest["identity"]["code_sha"] == PRE_SESSION_SHA:
            continue
        if manifest["identity"]["source_fingerprint"] not in imported:
            raise EvalSessionError("session_evidence_history_unverifiable")


def prepare_session(store: EvalEvidenceStore, state: Path,
                    selected: list[str] | None = None) -> str:
    plan, snapshot = campaign_config()
    identity = source_identity()
    validate_state_directory(state, dict(os.environ), sealed_image=True)
    if identity.get("worktree") != "clean" or identity.get("identity_source") != "sealed_image":
        raise EvalSessionError("session_clean_published_candidate_required")
    settings = gateway_settings(dict(os.environ))
    session = EvalValidationSession(store)
    session.validate(session_scope(ROOT, plan, snapshot), settings.litellm_proxy_virtual_key)
    if (session.folder / "worker.lease").exists():
        raise EvalSessionError("session_worker_active_or_uncertain")
    if session.summary()["gateway_observed"] is not True:
        raise EvalSessionError("session_gateway_unverified")
    attempts = session.summary()["attempts"]
    # Do not pay again for already passed cases; historic labels stay attached
    # to their original candidate, never certify the new candidate retroactively.
    passed = {item["case_id"] for item in attempts if item["status"] == "passed"}
    # Default selection runs only never-started cases. Uncertain/reserved/already
    # used cases are skipped, never retried; an explicit --cases stays strict.
    unavailable = {item["case_id"] for item in attempts if (
        item["status"] in {"uncertain", "reserved"}
        or item["source"] == identity["source_fingerprint"]
    )}
    case_ids = tuple(selected) if selected else tuple(
        c for c in plan.case_ids if c not in passed and c not in unavailable
    )
    if (not case_ids or len(set(case_ids)) != len(case_ids)
        or any(c not in plan.case_ids for c in case_ids)):
        raise EvalSessionError("session_case_selection_invalid_or_complete")
    per_case = min(Decimal(str(plan.budget.max_estimated_cost_usd)),
                   session.remaining() / len(case_ids)).quantize(Decimal("0.000001"), ROUND_DOWN)
    if per_case <= 0:
        raise EvalSessionError("session_budget_insufficient")
    for case_id in case_ids:
        if any(item["case_id"] == case_id and (
            item["source"] == identity["source_fingerprint"]
            or item["status"] in {"uncertain", "reserved"}
        ) for item in attempts):
            raise EvalSessionError("session_case_consumed_or_uncertain")
    selected_plan = plan.model_copy(update={
        "case_ids": case_ids,
        "budget": plan.budget.model_copy(update={"max_estimated_cost_usd": float(per_case)}),
    })
    cases = selected_plan.validate_snapshot(snapshot)
    # Do not let a changed subset or a lower per-case budget bypass the original
    # source/case anti-replay marker, even if its worker has not started yet.
    claim = session.folder / ("selection-" + identity["source_fingerprint"] + ".claimed")
    fd = os.open(claim, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="ascii") as file:
        file.write(selected_plan.checksum())
        file.flush()
        os.fsync(file.fileno())
    run_id = store.create(identity, selected_plan.model_dump(mode="json"),
                          [case_record(case) for case in cases],
                          snapshot.model_dump(mode="json", by_alias=True), synthetic_approved=True)
    store.append(run_id, "approval", {"gates": approval_gates(selected_plan, snapshot, identity),
                                      "validation_session": True,
                                      "scope": session_scope(ROOT, plan, snapshot)})
    return run_id


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
    import httpx

    from src.agent.eval_campaign import gateway_settings, verify_gateway_models
    from src.agent.eval_gateway_policy import validate_key_info

    settings = gateway_settings(env)
    base = settings.litellm_proxy_base_url.rstrip("/")
    async with httpx.AsyncClient(timeout=15, follow_redirects=False, trust_env=False) as client:
        headers = {"Authorization": "Bearer " + settings.litellm_proxy_virtual_key}
        response = await client.get(base.removesuffix("/v1") + "/key/info", headers=headers)
        response.raise_for_status()
        info = response.json()["info"]
        validate_key_info(info, plan, required=plan.total_estimated_cost_usd)
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
    decision = next(event["data"] for event in events if event["kind"] == "approval")
    approval = decision["gates"]
    plan = EvalCampaignPlan.model_validate(manifest["plan"])
    snapshot = RuntimeConfigSnapshot.model_validate(manifest["snapshot"])
    gated_env = {**env, **approval}
    try:
        if decision.get("validation_session") is True:
            session = EvalValidationSession(store)
            full_plan, full_snapshot = campaign_config()
            scope = session_scope(ROOT, full_plan, full_snapshot)
            if decision.get("scope") != scope:
                raise EvalSessionError("session_scope_or_key_changed")
            session.validate_selection(plan, full_plan)
            session.validate(scope,
                             gateway_settings(env).litellm_proxy_virtual_key)
            with session.worker(run_id, manifest["identity"]):
                await execute_approved(plan, snapshot, manifest["identity"], gated_env, state,
                                       durable=(store, run_id), validation_session=session)
            store.append(run_id, "session_budget", session.summary())
        else:
            await validate_reusable_access(plan, gated_env)
            await execute_approved(plan, snapshot, manifest["identity"], gated_env, state,
                                   durable=(store, run_id))
    except EvalSessionError as error:
        previous = next((event["data"] for event in reversed(store.events(run_id))
                         if event["kind"] == "checkpoint"), {})
        store.append(run_id, "checkpoint", {**previous, "status": "stopped",
                                             "session_reason": session_reason(str(error)),
                                             "error_class": "EvalSessionError",
                                             "inference_started": previous.get(
                                                 "inference_started", False,
                                             )})
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
      "promote", "export", "purge", "session-init", "session-status", "session-reclassify"])
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
    result.add_argument("--cases", nargs="+")
    result.add_argument("--accept-session", action="store_true")
    result.add_argument("--human", action="store_true",
                        help="readable summary for status/session-status; JSON by default")
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
            session = EvalValidationSession(store)
            if args.cases and not session.exists():
                raise EvalSessionError("session_required_for_case_selection")
            run_id = (prepare_session(store, state, args.cases) if session.exists()
                      else prepare(store, state, approval))
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
            if args.human:
                totals = {c["id"]: len(c["criteria"])
                          for c in store.manifest(args.run_id)["cases"]}
                print(human_status(report, totals))
                return 0
        elif args.command == "list":
            report = {"runs": store.runs()}
        elif args.command == "session-init":
            if not args.accept_session:
                raise EvalSessionError("session_initial_acceptance_required")
            plan, snapshot = campaign_config()
            identity = source_identity()
            validate_state_directory(state, dict(os.environ), sealed_image=True)
            if (identity.get("worktree") != "clean"
                or identity.get("identity_source") != "sealed_image"):
                raise EvalSessionError("session_clean_published_candidate_required")
            session = EvalValidationSession(store)
            history = session_history(state, plan) if not session.exists() else []
            if not session.exists():
                verify_imported_runs(store, history)
                if list(state.glob(plan.checksum() + "*.reserved.json")) and not history:
                    raise EvalSessionError("session_history_unverifiable")
            report = session.initialize(
                scope=session_scope(ROOT, plan, snapshot), plan=plan,
                key=gateway_settings(dict(os.environ)).litellm_proxy_virtual_key,
                history=history,
            )
            report = asyncio.run(check_session_access(session, plan, dict(os.environ)))
        elif args.command == "session-status":
            report = EvalValidationSession(store).summary()
            if args.human:
                print(human_session(report))
                return 0
        elif args.command == "session-reclassify":
            plan, snapshot = campaign_config()
            validate_state_directory(state, dict(os.environ), sealed_image=True)
            session = EvalValidationSession(store)
            session.validate(session_scope(ROOT, plan, snapshot),
                             gateway_settings(dict(os.environ)).litellm_proxy_virtual_key)
            if (session.folder / "worker.lease").exists():
                raise EvalSessionError("session_worker_active_or_uncertain")
            changed = session.reclassify_imported(session_history(state, plan))
            report = {**session.summary(), "reclassified_cases": changed}
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
    except EvalSessionError as error:
        print(json.dumps({"status": "eval_session_blocked", "reason": session_reason(str(error)),
                          "inference_started": False, "do_not_replay": True}))
        return 1
    except (Exception, KeyboardInterrupt) as error:
        print(json.dumps({"status": "eval_console_blocked_or_disconnected",
                          "reason": console_failure_reason(error),
                          "do_not_replay": True, "review_can_reopen_saved_evidence": True}))
        return 1
    finally:
        logging.disable(disabled)


if __name__ == "__main__":
    raise SystemExit(main())
