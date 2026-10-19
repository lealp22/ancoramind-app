"""One encrypted, cumulative eval allowance; not permission for automatic retries."""

from __future__ import annotations

import hashlib
import os
import re
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx

from src.agent.eval_campaign import EvalCampaignPlan, verify_gateway_models
from src.agent.eval_campaign_runner import campaign_cases_fingerprint
from src.agent.eval_evidence import EvalEvidenceStore, digest
from src.domain.llm_access.context import current_execution_context
from src.domain.llm_access.models import LlmUsageEventCreate
from src.domain.runtime_config.models import RuntimeConfigSnapshot

LIMIT = Decimal("0.10")
# Only diagnostic/operational harness changes inherit the same spending scope.
# Product/runtime/prompts/tools/catalog changes require a distinct scope decision.
_HARNESS = {
    "src/agent/eval_validation_session.py", "src/agent/eval_diagnostics.py",
    "src/agent/eval_gateway_policy.py",
    "src/agent/eval_evidence.py", "src/agent/eval_campaign.py",
    "src/agent/eval_campaign_runner.py", "src/agent/eval_durable_review.py",
    "src/agent/eval_physical_executor.py", "scripts/eval_console.py",
    "scripts/execute_eval_campaign.py", "scripts/deploy_eval_candidate.py",
    "scripts/eval_source.py", "scripts/prepare_eval_build.py",
}


class EvalSessionError(ValueError):
    """Only fixed, content-free codes are safe to display."""


def session_reason(value: object) -> str | None:
    codes = {
        "session_budget_unverifiable", "session_budget_insufficient",
        "session_gateway_unverified", "session_gateway_spend_decreased",
        "session_scope_or_key_changed", "session_case_consumed_or_uncertain",
        "session_paid_route_not_reserved", "session_case_cost_exceeded", "session_expired",
        "session_history_unverifiable", "session_ledger_invalid", "session_path_invalid",
        "session_scope_unverifiable", "session_prior_execution_not_terminal",
        "session_clean_published_candidate_required", "session_worker_active_or_uncertain",
        "session_case_selection_invalid_or_complete", "session_required_for_case_selection",
        "session_initial_acceptance_required", "session_evidence_history_unverifiable",
    }
    return value if isinstance(value, str) and value in codes else None


def amount(value: object) -> Decimal:
    try:
        result = Decimal(str(value))
    except Exception:
        raise EvalSessionError("session_budget_unverifiable") from None
    if not result.is_finite() or result < 0:
        raise EvalSessionError("session_budget_unverifiable")
    return result


def session_scope(root: Path, plan: EvalCampaignPlan, snapshot: RuntimeConfigSnapshot) -> str:
    files: list[Path] = []
    for folder, pattern in (("src", "*.py"), ("scripts", "*.py"), ("prompts", "*.md"),
                            ("evals", "*.json")):
        files.extend((root / folder).rglob(pattern))
    files.extend(root / name for name in (
        "pyproject.toml", "evals/Dockerfile", "evals/Dockerfile.dockerignore",
    ))
    hashes = {}
    for path in sorted(set(files)):
        name = path.relative_to(root).as_posix()
        if name in _HARNESS:
            continue
        if path.is_symlink() or not path.is_file():
            raise EvalSessionError("session_scope_unverifiable")
        hashes[name] = hashlib.sha256(
            path.read_text(encoding="utf-8").replace("\r\n", "\n").encode(),
        ).hexdigest()
    return digest({"files": hashes, "plan": plan.checksum(),
                   "cases": campaign_cases_fingerprint(plan.validate_snapshot(snapshot))})


class EvalValidationSession:
    """Single private volume/key, atomic ciphertext ledger and exclusive worker lease.

    Uncertain cost keeps a full case reservation. A dead worker never gets an
    automatic replacement, release or budget reset. No exact invoice guarantee.
    """

    def __init__(self, evidence: EvalEvidenceStore):
        self.storage = evidence
        self.folder = evidence.root / "validation-session"
        if self.folder.is_symlink():
            raise EvalSessionError("session_path_invalid")
        self.folder.mkdir(mode=0o700, exist_ok=True)
        self.path = self.folder / "ledger.enc"
        self.active_case: tuple[str, str] | None = None
        self.blocked_reason: str | None = None

    def _read(self) -> dict[str, Any]:
        value = self.storage._read(self.path)
        if value.get("version") != 1 or amount(value.get("limit")) != LIMIT:
            raise EvalSessionError("session_ledger_invalid")
        for name in ("scope", "key_binding", "base_plan"):
            if (not isinstance(value.get(name), str)
                or not re.fullmatch(r"[a-f0-9]{64}", value[name])):
                raise EvalSessionError("session_ledger_invalid")
        if (type(value.get("gateway_observed")) is not bool
            or type(value.get("baseline_set")) is not bool) or not isinstance(
            value.get("attempts"), list,
        ):
            raise EvalSessionError("session_ledger_invalid")
        amount(value.get("gateway_spend"))
        amount(value.get("gateway_baseline"))
        for item in value["attempts"]:
            if (not isinstance(item, dict) or item.get("status") not in {
                "passed", "failed", "uncertain", "reserved",
            } or not isinstance(item.get("source"), str)
                or not re.fullmatch(r"[a-f0-9]{64}", item["source"])
                or not isinstance(item.get("run_id"), str)
                or not re.fullmatch(r"[a-f0-9]{32}|legacy:[a-f0-9]{64}", item["run_id"])
                or not isinstance(item.get("case_id"), str)
                or not re.fullmatch(r"response_style\.[a-z_]+", item["case_id"])):
                raise EvalSessionError("session_ledger_invalid")
            amount(item.get("charged"))
            if type(item.get("imported")) is not bool:
                raise EvalSessionError("session_ledger_invalid")
        if not isinstance(value.get("candidates"), list):
            raise EvalSessionError("session_ledger_invalid")
        expiry = datetime.fromisoformat(value["expires"])
        if expiry.tzinfo is None or datetime.now(UTC) >= expiry:
            raise EvalSessionError("session_expired")
        return value

    def check_history(self, history: list[dict[str, Any]], plan: EvalCampaignPlan) -> None:
        ids = set(plan.case_ids)
        for run in history:
            if not re.fullmatch(r"[a-f0-9]{64}", run["source"]):
                raise EvalSessionError("session_history_unverifiable")
            seen = set()
            for item in run["results"]:
                if item.get("case_id") not in ids or item["case_id"] in seen:
                    raise EvalSessionError("session_history_unverifiable")
                seen.add(item["case_id"])
            if seen != ids:
                raise EvalSessionError("session_history_unverifiable")

    def validate_selection(self, plan: EvalCampaignPlan, baseline: EvalCampaignPlan) -> None:
        if (not set(plan.case_ids) <= set(baseline.case_ids)
            or plan.total_estimated_cost_usd != baseline.total_estimated_cost_usd
            or plan.logical_route != baseline.logical_route
            or plan.effective_gateway_route != baseline.effective_gateway_route
            or plan.config_revision != baseline.config_revision
            or plan.snapshot_checksum != baseline.snapshot_checksum
            or plan.snapshot_fingerprint != baseline.snapshot_fingerprint
            or any(value != getattr(baseline.budget, name) for name, value
                   in plan.budget.model_dump().items() if name != "max_estimated_cost_usd")
            or plan.budget.max_estimated_cost_usd is None
            or baseline.budget.max_estimated_cost_usd is None
            or plan.budget.max_estimated_cost_usd > baseline.budget.max_estimated_cost_usd):
            raise EvalSessionError("session_scope_or_key_changed")

    def _save(self, value: dict[str, Any]) -> None:
        temporary = self.folder / ("ledger-" + uuid4().hex + ".enc")
        try:
            self.storage._write(temporary, value)
            if self.path.is_symlink():
                raise EvalSessionError("session_path_invalid")
            os.replace(temporary, self.path)
            if os.name != "nt":
                fd = os.open(self.folder, os.O_RDONLY)
                try:
                    os.fsync(fd)
                finally:
                    os.close(fd)
        finally:
            temporary.unlink(missing_ok=True)

    @staticmethod
    def _charged(value: dict[str, Any]) -> Decimal:
        imported = sum((amount(i["charged"]) for i in value["attempts"]
                        if i.get("imported") is True), Decimal(0))
        current = sum((amount(i["charged"]) for i in value["attempts"]
                       if i.get("imported") is not True), Decimal(0))
        return max(amount(value["gateway_spend"]),
                   max(imported, amount(value["gateway_baseline"])) + current)

    def initialize(self, *, scope: str, plan: EvalCampaignPlan, key: str,
                   history: list[dict[str, Any]]) -> dict[str, Any]:
        binding = hashlib.sha256(key.encode()).hexdigest()
        with self.storage._lock(self.folder):
            if self.path.exists():
                value = self._read()
                if value["scope"] != scope or value["key_binding"] != binding:
                    raise EvalSessionError("session_scope_or_key_changed")
                return self.summary(value)
            attempts = []
            self.check_history(history, plan)
            for run in history:
                for result in run["results"]:
                    if result.get("status") == "not_started":
                        continue
                    if result.get("status") not in {"passed", "stopped", "started"}:
                        raise EvalSessionError("session_history_unverifiable")
                    # Legacy actual_cost=null or failed output is NOT free. Import
                    # full approved case ceiling; never trust an estimate as invoice.
                    attempts.append({
                        "run_id": run["run_id"], "source": run["source"],
                        "imported": True,
                        "case_id": result["case_id"],
                        "charged": str(plan.budget.max_estimated_cost_usd),
                        "status": ("passed" if result["status"] == "passed" else "failed"
                                   if run.get("usage_complete") and result.get("error_class")
                                   == "InvalidPresentationOutputError" else "uncertain"),
                    })
            value = {
                "version": 1, "scope": scope, "key_binding": binding,
                "limit": str(LIMIT), "gateway_spend": "0", "gateway_observed": False,
                "gateway_baseline": "0",
                "baseline_set": False,
                "expires": (datetime.now(UTC) + timedelta(days=7)).isoformat(),
                "attempts": attempts, "candidates": [], "base_plan": plan.checksum(),
            }
            # Persist already-consumed history even when it exhausts this session;
            # never reject import in a way that would invite starting from zero.
            self._save(value)
            return self.summary(value)

    def validate(self, scope: str, key: str) -> None:
        value = self._read()
        if (value["scope"] != scope
            or value["key_binding"] != hashlib.sha256(key.encode()).hexdigest()):
            raise EvalSessionError("session_scope_or_key_changed")

    def exists(self) -> bool:
        return self.path.exists()

    def remaining(self) -> Decimal:
        return max(Decimal(0), LIMIT - self._charged(self._read()))

    def summary(self, value: dict[str, Any] | None = None) -> dict[str, Any]:
        value = self._read() if value is None else value
        charged = self._charged(value)
        return {"status": "session_ready", "limit_usd": str(LIMIT),
                "budget_basis": "conservative_reservations_not_invoice",
                "charged_or_reserved_usd": str(charged),
                "available_usd": str(max(Decimal(0), LIMIT - charged)),
                "gateway_spend_usd": value["gateway_spend"],
                "gateway_observed": value["gateway_observed"], "expires": value["expires"],
                "attempts": [{k: item[k] for k in (
                    "run_id", "source", "case_id", "charged", "status",
                )} for item in value["attempts"]], "inference_started": False}

    @contextmanager
    def worker(self, run_id: str, identity: Mapping[str, str]) -> Iterator[None]:
        # Exclusive lease remains on a hard crash; inspection, not PID reuse,
        # must resolve it. Never clear someone else's lease on command failure.
        lease = self.folder / "worker.lease"
        fd = os.open(lease, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="ascii") as file:
            file.write(run_id)
            file.flush()
            os.fsync(file.fileno())
        try:
            with self.storage._lock(self.folder):
                value = self._read()
                candidate = {"run_id": run_id, "code_sha": identity["code_sha"],
                             "source_fingerprint": identity["source_fingerprint"]}
                value["candidates"].append(candidate)
                self._save(value)
            yield
        finally:
            lease.unlink()

    def observe_gateway(self, info: dict[str, Any], key: str, plan: EvalCampaignPlan) -> Decimal:
        from src.agent.eval_gateway_policy import validate_key_info

        validate_key_info(info, plan, required=Decimal(0), maximum=LIMIT)
        if amount(info["max_budget"]) != LIMIT:
            raise EvalSessionError("session_budget_unverifiable")
        spend = amount(info.get("spend"))
        with self.storage._lock(self.folder):
            value = self._read()
            if value["key_binding"] != hashlib.sha256(key.encode()).hexdigest():
                raise EvalSessionError("session_scope_or_key_changed")
            if spend < amount(value["gateway_spend"]):
                raise EvalSessionError("session_gateway_spend_decreased")
            if not value["baseline_set"]:
                value["gateway_baseline"] = str(spend)
            value.update(gateway_spend=str(spend), gateway_observed=True, baseline_set=True)
            self._save(value)
        return spend

    def gateway_error(self, code: str) -> None:
        with self.storage._lock(self.folder):
            value = self._read()
            value["gateway_observed"] = False
            self._save(value)
        self.blocked_reason = session_reason(code) or "session_budget_unverifiable"

    def reserve(self, run_id: str, case_id: str, source: str, ceiling: Decimal) -> None:
        if (not re.fullmatch(r"[a-f0-9]{32}", run_id)
            or not re.fullmatch(r"[a-f0-9]{64}", source)
            or not re.fullmatch(r"response_style\.[a-z_]+", case_id)
            or not ceiling.is_finite()):
            raise EvalSessionError("session_budget_unverifiable")
        with self.storage._lock(self.folder):
            value = self._read()
            if not value["gateway_observed"]:
                raise EvalSessionError("session_gateway_unverified")
            if any(item["case_id"] == case_id and (
                item["source"] == source or item["status"] in {"uncertain", "reserved"}
            ) for item in value["attempts"]):
                raise EvalSessionError("session_case_consumed_or_uncertain")
            if ceiling <= 0 or self._charged(value) + ceiling > LIMIT:
                raise EvalSessionError("session_budget_insufficient")
            if ceiling > Decimal("0.02"):
                raise EvalSessionError("session_budget_insufficient")
            value["attempts"].append({"run_id": run_id, "source": source, "case_id": case_id,
                                      "imported": False,
                                      "charged": str(ceiling), "status": "reserved"})
            self._save(value)
        self.active_case = (run_id, case_id)

    def settle(self, events: list[LlmUsageEventCreate], *, passed: bool) -> None:
        if self.active_case is None:
            return
        with self.storage._lock(self.folder):
            value = self._read()
            item = next(i for i in value["attempts"]
                        if (i["run_id"], i["case_id"]) == self.active_case)
            completed = bool(events) and all(e.status == "completed" for e in events)
            if events:
                charge = max(sum((amount(e.actual_cost) for e in events
                                  if e.actual_cost is not None), Decimal(0)),
                             sum((amount(e.estimated_cost) for e in events
                                  if e.estimated_cost is not None), Decimal(0)))
                if charge > amount(item["charged"]):
                    item.update(status="uncertain", charged=str(charge))
                    self._save(value)
                    raise EvalSessionError("session_case_cost_exceeded")
                # Even a metadata cost can lag the Gateway. Keep the approved
                # case reservation until explicit operator accounting, never
                # present estimates/partial usage as fresh spendable allowance.
            item["status"] = ("passed" if passed and completed else
                              "failed" if completed else "uncertain")
            self._save(value)
        self.active_case = None

    async def before_request(self, request: httpx.Request) -> None:
        """Check cumulative allowance immediately before each paid Gateway request."""
        if request.method != "POST":
            return
        if (request.url.path != "/v1/chat/completions" or self.active_case is None):
            raise EvalSessionError("session_paid_route_not_reserved")
        budget = current_execution_context().budget
        cumulative_estimate = amount(budget.estimated_cost_usd)
        value = self._read()
        if value["gateway_observed"] is not True:
            raise EvalSessionError("session_gateway_unverified")
        reservation = amount(next(item["charged"] for item in value["attempts"]
                                  if (item["run_id"], item["case_id"]) == self.active_case))
        if (amount(value["gateway_spend"]) >= LIMIT or cumulative_estimate > reservation
            or amount(value["gateway_spend"]) + reservation > LIMIT
            or self._charged(value) > LIMIT):
            raise EvalSessionError("session_budget_insufficient")


async def read_session_gateway(client: httpx.AsyncClient, base: str, key: str,
                               plan: EvalCampaignPlan, session: EvalValidationSession) -> None:
    headers = {"Authorization": "Bearer " + key}
    try:
        response = await client.get(base.removesuffix("/v1") + "/key/info", headers=headers)
        response.raise_for_status()
        session.observe_gateway(response.json()["info"], key, plan)
        response = await client.get(base + "/models", headers=headers)
        response.raise_for_status()
        verify_gateway_models(response.json(), plan.effective_gateway_route)
    except Exception as error:
        code = session_reason(str(error)) if isinstance(error, EvalSessionError) else None
        session.gateway_error(code or "session_budget_unverifiable")
        raise EvalSessionError(code or "session_budget_unverifiable") from None
