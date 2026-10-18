"""Operator-controlled smoke and separately approved five-case campaign.

Run by stdin, never copy into the sealed eval image. Admin uses only loopback
management routes; smoke uses existing LLMAccess, no Agent/tools/business DB.
Secrets enter/leave only through private TTY; reports and durable state are
metadata-only. A reserved/ambiguous run MUST NOT be replayed with another key.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import getpass
import hashlib
import json
import logging
import os
import re
import sys
import time
import uuid
import warnings
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

ALIAS = "ancoramind-default-r4"
PREFIX = "ancoramind-evals-accounting-"
READ_ROUTES = ["/models", "/v1/models", "/key/info"]
SMOKE_ROUTES = [*READ_ROUTES, "/v1/chat/completions", "/chat/completions"]
SHA = "db0c59be0b2eeb807d4222aeb5a62b622d90b200"
SOURCE = "108c410d26149cd5e3946e15d16f728fdfbdd4f6a8553fef1ec787df271e6c82"
PLAN = "8f3e4a51496dbbdc763fd17458e8857fe785bd8abaf6016881effe6f79bd8139"
ROOT = Path("/app")
STATE = Path("/eval-state")
RESERVATION = "accounting-smoke-v1.reserved.json"
REPORT = "accounting-smoke-v1.report.json"
CASES = "abddf11d06c5233ca97ddf016938ae759f698b740588167c5a9079dc5d137474"


@dataclass(frozen=True)
class KeyPolicy:
    name: str
    prefix: str
    budget: str
    duration: str
    minutes: int
    rpm: int
    tpm: int


SMOKE_POLICY = KeyPolicy("smoke", PREFIX, "0.01", "30m", 30, 1, 2000)
CAMPAIGN_POLICY = KeyPolicy(
    "campaign", "ancoramind-evals-campaign-", "0.10", "2h", 120, 30, 250000,
)


def finite(value: object) -> Decimal:
    result = Decimal(str(value))
    if not result.is_finite() or result < 0:
        raise ValueError("invalid_cost")
    return result


def key_metadata(info: dict, now: datetime, policy: KeyPolicy = SMOKE_POLICY) -> dict:
    expires = datetime.fromisoformat(info["expires"].replace("Z", "+00:00"))
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=UTC)
    if (
        not str(info.get("key_alias", "")).startswith(policy.prefix)
        or info.get("models") != [ALIAS]
        or set(info.get("allowed_routes") or []) != set(SMOKE_ROUTES)
        or finite(info.get("max_budget")) != Decimal(policy.budget)
        or info.get("budget_duration") is not None or info.get("budget_reset_at") is not None
        or info.get("max_parallel_requests") != 1
        or info.get("rpm_limit") != policy.rpm or info.get("tpm_limit") != policy.tpm
        or info.get("blocked") or info.get("auto_rotate")
        or not now + timedelta(seconds=45) < expires <= now + timedelta(minutes=policy.minutes + 2)
    ):
        raise ValueError("smoke_key_restrictions_mismatch")
    for field in ("aliases", "config", "permissions"):
        value = info.get(field)
        if isinstance(value, str):
            value = json.loads(value)
        if value is not None and value != {}:
            raise ValueError("smoke_key_overrides_forbidden")
    return {"key_alias": info["key_alias"], "expires": expires.isoformat(),
            "spend_usd": str(finite(info.get("spend")))}


def key_payload(alias: str, policy: KeyPolicy = SMOKE_POLICY) -> dict:
    return {
        "key_alias": alias, "models": [ALIAS], "duration": policy.duration,
        "key_type": "default", "allowed_routes": SMOKE_ROUTES,
        "max_budget": float(policy.budget), "budget_duration": None, "spend": 0,
        "max_parallel_requests": 1, "rpm_limit": policy.rpm, "tpm_limit": policy.tpm,
        "auto_rotate": False, "send_invite_email": False,
        "metadata": {"service": "ancoramind-evals", "purpose": "one-" + policy.name},
    }


def admin_call(method: str, route: str, token: str, payload: dict | None = None) -> dict:
    from urllib.parse import urlsplit
    from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

    if (method, urlsplit(route).path) not in {
        ("POST", "/key/generate"), ("POST", "/key/delete"),
        ("GET", "/key/info"), ("GET", "/key/list"), ("GET", "/v1/models"),
    }:
        raise ValueError("admin_route_forbidden")
    port = os.environ.get("PORT", "4000")
    if not re.fullmatch(r"[0-9]{1,5}", port) or not 1 <= int(port) <= 65535:
        raise ValueError("admin_port_invalid")

    class NoRedirect(HTTPRedirectHandler):
        def redirect_request(self, *_args, **_kwargs):
            return None

    request = Request("http://127.0.0.1:" + port + route, method=method,
                      data=None if payload is None else json.dumps(payload).encode(),
                      headers={"Authorization": "Bearer " + token,
                               "Content-Type": "application/json"})
    with build_opener(ProxyHandler({}), NoRedirect()).open(request, timeout=15) as response:
        return json.load(response)


def revoke(alias: str, key: str, master: str, call=admin_call) -> None:
    from urllib.parse import urlencode

    deleted = call("POST", "/key/delete", master, {"keys": [key]})
    if not set(deleted.get("deleted_keys") or []) & {
        key, hashlib.sha256(key.encode()).hexdigest(),
    }:
        raise ValueError("cleanup_unconfirmed")
    listed = call("GET", "/key/list?" + urlencode({"key_alias": alias, "size": 2}), master)
    if listed.get("total_count") != 0:
        raise ValueError("cleanup_unconfirmed")


def admin(console, reader, call=admin_call, *, policy: KeyPolicy = SMOKE_POLICY) -> int:
    """Create only when operator is ready; terminal stays open until cleanup."""
    master = os.environ.get("LITELLM_MASTER_KEY", "").strip()
    if not master or not console.isatty():
        raise ValueError("existing_gateway_private_shell_required")
    alias = policy.prefix + uuid.uuid4().hex[:12]
    key = None
    try:
        created = call("POST", "/key/generate", master, key_payload(alias, policy))
        key = created.get("key")
        if not isinstance(key, str) or not key.startswith("sk-"):
            key = None
            raise ValueError("creation_ambiguous")
        info = key_metadata(call("GET", "/key/info", key)["info"], datetime.now(UTC), policy)
        if info["key_alias"] != alias or finite(info["spend_usd"]) != 0:
            raise ValueError("new_key_mismatch")
        visible = call("GET", "/v1/models", key)["data"]
        if not visible or {row.get("id") for row in visible} != {ALIAS}:
            raise ValueError("model_scope_mismatch")
        console.write("\nCLAVE " + policy.name.upper()
                      + " — sólo al prompt oculto del evaluador, nunca al chat:\n")
        console.write(key + "\n")
        console.flush()
        print(json.dumps({"status": policy.name + "_key_ready", **info,
                          "max_budget_usd": policy.budget, "inference_started": False,
                          "campaign_approved": policy == CAMPAIGN_POLICY}), flush=True)
        console.write("Mantén esta shell abierta. Ejecuta " + policy.name + " en la otra shell.\n"
                      "AL TERMINAR o cancelar, pulsa Enter aquí para REVOCAR la clave.\n")
        console.flush()
        reader.readline()
        return 0
    except (Exception, KeyboardInterrupt):
        print(json.dumps({"status": policy.name + "_key_blocked_or_ambiguous", "key_alias": alias,
                          "do_not_repeat_creation": True, "inference_started": False}))
        return 1
    finally:
        if key is not None:
            try:
                revoke(alias, key, master, call)
                print(json.dumps({"status": policy.name + "_key_revoked_verified",
                                  "key_alias": alias}))
            except Exception:
                print(json.dumps({"status": policy.name + "_key_cleanup_unconfirmed",
                                  "key_alias": alias}))


async def smoke(env: dict, key: str, *, transport=None) -> dict:
    """ONE governed model primitive; any attempted POST consumes the reservation."""
    import httpx
    from agno.models.message import Message

    from scripts.eval_source import source_identity
    from scripts.execute_eval_campaign import validate_state_directory
    from src.agent.eval_campaign import EvalCampaignPlan, gateway_settings, verify_gateway_models
    from src.agent.llm_access import AgnoLLMAccess
    from src.domain.llm_access.context import execution_context_scope
    from src.domain.llm_access.models import ExecutionBudget, ExecutionContext
    from src.domain.runtime_config.models import RuntimeConfigSnapshot

    if env.get("ANCORA_EVAL_ACCOUNTING_SMOKE_APPROVED") != "one-call-0.01-usd":
        raise ValueError("explicit_smoke_approval_required")
    identity = source_identity(ROOT)
    if (identity.get("code_sha"), identity.get("source_fingerprint"),
        identity.get("identity_source")) != (SHA, SOURCE, "sealed_image"):
        raise ValueError("candidate_mismatch")
    folder = ROOT / "evals" / "response_style"
    snapshot = RuntimeConfigSnapshot.model_validate_json(
        (folder / "runtime-rev8-snapshot.json").read_text()
    )
    plan = EvalCampaignPlan.model_validate_json((folder / "bl48-campaign-plan.json").read_text())
    cases = plan.validate_snapshot(snapshot)
    if plan.checksum() != PLAN or len(cases[0].input_text) > 2000:
        raise ValueError("plan_mismatch")
    validate_state_directory(STATE, env, sealed_image=True)
    settings = gateway_settings({"ANCORA_EVAL_GATEWAY_URL": env.get("ANCORA_EVAL_GATEWAY_URL", ""),
                                 "ANCORA_EVAL_GATEWAY_KEY": key})
    base = settings.litellm_proxy_base_url.rstrip("/")
    origin = httpx.URL(base).copy_with(path="/", query=None)
    post_count = 0
    cost_header = None

    async def guard(request):
        nonlocal post_count
        if request.url.copy_with(path="/", query=None) != origin:
            raise ValueError("unexpected_http_origin")
        if request.method == "GET" and request.url.path in {"/v1/models", "/key/info"}:
            return
        if request.method != "POST" or request.url.path != "/v1/chat/completions":
            raise ValueError("unexpected_http_request")
        body = json.loads(request.content)
        if (post_count or body.get("model") != ALIAS or body.get("max_tokens") != 64
            or body.get("tools") or body.get("stream") or body.get("num_retries") != 0
            or body.get("fallbacks") != [] or body.get("provider") != {"allow_fallbacks": False}):
            raise ValueError("smoke_request_limits_mismatch")
        post_count += 1

    async def record_header(response):
        nonlocal cost_header
        if response.request.method == "POST":
            raw = response.headers.get("x-litellm-response-cost")
            if raw is not None:
                cost_header = str(finite(raw))

    report = {"status": "smoke_preflight", "code_sha": SHA, "source_fingerprint": SOURCE,
              "plan_checksum": PLAN, "inference_started": False, "campaign_approved": False}
    async with httpx.AsyncClient(
        timeout=15, follow_redirects=False, trust_env=False,
        transport=transport or httpx.AsyncHTTPTransport(retries=0),
        event_hooks={"request": [guard], "response": [record_header]},
    ) as client:
        async def info():
            response = await client.get(base.removesuffix("/v1") + "/key/info",
                                        headers={"Authorization": "Bearer " + key})
            response.raise_for_status()
            return key_metadata(response.json()["info"], datetime.now(UTC))

        before = await info()
        if finite(before["spend_usd"]) != 0:
            raise ValueError("smoke_key_already_used")
        visible = await client.get(base + "/models", headers={"Authorization": "Bearer " + key})
        visible.raise_for_status()
        verify_gateway_models(visible.json(), ALIAS)
        report.update(key_alias=before["key_alias"], spend_before_usd=before["spend_usd"])
        if (STATE / REPORT).exists() or (STATE / REPORT).is_symlink():
            raise ValueError("smoke_report_exists_do_not_replay")
        # Separate from campaign reservation: never consume/erase its plan marker.
        with (STATE / RESERVATION).open("x", encoding="utf-8") as file:
            json.dump({**report, "status": "consumed_do_not_replay"}, file)
            file.flush()
            os.fsync(file.fileno())
        report["inference_started"] = True
        # Reject an existing/symlink report before any POST; never overwrite prior evidence.
        with (STATE / REPORT).open("x", encoding="utf-8") as file:
            json.dump(report, file)
        def checkpoint():
            with (STATE / REPORT).open("w", encoding="utf-8") as file:
                json.dump(report, file)
                file.flush()
                os.fsync(file.fileno())
        checkpoint()
        events = []
        stage = "model_setup"
        async def record(event):
            events.append(event)
        try:
            budget_config = plan.budget.model_copy(update={
                "max_model_calls": 1, "max_gateway_requests": 1,
                "max_gateway_attempts_per_model_call": 1, "max_runtime_seconds": 30,
                "max_output_tokens": 64, "max_estimated_cost_usd": 0.01,
            })
            context = ExecutionContext(
                correlation_id=uuid.uuid4(), telegram_update_id=0,
                agno_run_id="accounting-smoke", agno_session_id="isolated-accounting-smoke",
                config=snapshot, budget=ExecutionBudget.from_config(
                    budget_config, started_at_monotonic=time.monotonic(),
                ),
            )
            model = AgnoLLMAccess(settings=settings, usage_recorder=record).model_for(
                plan.logical_route, context,
            )
            model.max_tokens = 64
            model.max_retries = 0
            model.retries = 0
            model.timeout = 30
            model.http_client = client
            model.extra_body = {"num_retries": 0, "fallbacks": [],
                                "provider": {"allow_fallbacks": False}}
            # Existing synthetic fixture, no new prompt/context or tools and no Agent loop.
            stage = "single_model_call"
            with execution_context_scope(context):
                await asyncio.wait_for(model.ainvoke(
                    [Message(role="user", content=cases[0].input_text)],
                    Message(role="assistant"),
                ), timeout=30)
            if post_count != 1 or len(events) != 1 or events[0].status != "completed":
                raise ValueError("unexpected_model_call_count")
            report.update(post_count=post_count, recorded_model_calls=len(events),
                          snapshot_estimate_usd=str(events[0].estimated_cost),
                          gateway_response_cost_usd=cost_header)
            # Read-only, bounded polling; never another inference.
            stage = "spend_reconciliation"
            for attempt in range(6):
                after = await info()
                delta = finite(after["spend_usd"]) - finite(before["spend_usd"])
                if delta > 0:
                    report.update(spend_after_usd=after["spend_usd"], spend_delta_usd=str(delta))
                    if delta > Decimal("0.01"):
                        raise ValueError("smoke_cost_exceeded")
                    if (
                        cost_header is not None
                        and abs(delta - finite(cost_header)) > Decimal("0.00000001")
                    ):
                        raise ValueError("smoke_cost_mismatch")
                    report["status"] = "smoke_accounting_verified"
                    break
                if attempt < 5:
                    await asyncio.sleep(2)
            else:
                report["status"] = "smoke_spend_not_observed_do_not_replay"
        except (Exception, asyncio.CancelledError):
            report.update(status="smoke_failed_or_ambiguous_do_not_replay", post_count=post_count,
                          stage=stage)
        finally:
            report["permission_cleanup_required"] = True
            checkpoint()
        return report


async def campaign(env: dict, key: str, *, transport=None) -> dict:
    """Run the EXISTING sealed harness once, with the owner's exact approval."""
    import httpx

    from scripts.eval_source import source_identity
    from scripts.execute_eval_campaign import execute_approved, validate_state_directory
    from src.agent.eval_campaign import EvalCampaignPlan, gateway_settings
    from src.agent.eval_campaign_runner import campaign_cases_fingerprint
    from src.domain.runtime_config.models import RuntimeConfigSnapshot

    if env.get("ANCORA_EVAL_CAMPAIGN_OPERATOR_APPROVED") != "five-cases-0.10-usd-once":
        raise ValueError("campaign_explicit_approval_required")
    identity = source_identity(ROOT)
    if (identity.get("code_sha"), identity.get("source_fingerprint"),
        identity.get("identity_source"), identity.get("worktree")) != (
            SHA, SOURCE, "sealed_image", "clean",
        ):
        raise ValueError("campaign_candidate_mismatch")
    folder = ROOT / "evals" / "response_style"
    snapshot = RuntimeConfigSnapshot.model_validate_json(
        (folder / "runtime-rev8-snapshot.json").read_text()
    )
    plan = EvalCampaignPlan.model_validate_json((folder / "bl48-campaign-plan.json").read_text())
    cases = plan.validate_snapshot(snapshot)
    if plan.checksum() != PLAN or campaign_cases_fingerprint(cases) != CASES:
        raise ValueError("campaign_plan_or_cases_mismatch")
    validate_state_directory(STATE, env, sealed_image=True)
    if (STATE / (PLAN + ".reserved.json")).exists() or (STATE / (PLAN + ".report.json")).exists():
        raise ValueError("campaign_already_consumed")
    settings = gateway_settings({
        "ANCORA_EVAL_GATEWAY_URL": env.get("ANCORA_EVAL_GATEWAY_URL", ""),
        "ANCORA_EVAL_GATEWAY_KEY": key,
    })
    gateway = settings.litellm_proxy_base_url.rstrip("/")
    async with httpx.AsyncClient(
        timeout=15, follow_redirects=False, trust_env=False,
        transport=transport or httpx.AsyncHTTPTransport(retries=0),
    ) as client:
        async def info():
            response = await client.get(gateway.removesuffix("/v1") + "/key/info",
                                        headers={"Authorization": "Bearer " + key})
            response.raise_for_status()
            return key_metadata(response.json()["info"], datetime.now(UTC), CAMPAIGN_POLICY)

        before = await info()
        if finite(before["spend_usd"]) != 0:
            raise ValueError("campaign_key_already_used")
        # Values encode the explicit owner decision, not a self-granted permission.
        approved_env = {
            "ANCORA_EVAL_APPROVED_PLAN": PLAN, "ANCORA_EVAL_APPROVED_SHA": SHA,
            "ANCORA_EVAL_APPROVED_SOURCE": SOURCE, "ANCORA_EVAL_APPROVED_CASES": CASES,
            "ANCORA_EVAL_SYNTHETIC_APPROVED": "1",
            "ANCORA_EVAL_EXTERNAL_BUDGET_VERIFIED": "1",
            "ANCORA_EVAL_SNAPSHOT_PROVENANCE_ACCEPTED": "1",
            "ANCORA_EVAL_HUMAN_REVIEW_APPROVED": "1",
            "ANCORA_EVAL_GATEWAY_URL": gateway, "ANCORA_EVAL_GATEWAY_KEY": key,
            "ANCORA_EVAL_REQUIRE_VOLUME": "1",
        }
        report = await execute_approved(plan, snapshot, identity, approved_env, STATE)
        report["campaign_approved"] = True
        report["permission_cleanup_required"] = True
        report["gateway_spend"] = {
            "key_alias": before["key_alias"], "before_usd": before["spend_usd"],
            "status": "not_observed",
        }
        # This cannot invoke inference; failed/uncertain campaign is never replayed.
        try:
            for attempt in range(6):
                after = await info()
                delta = finite(after["spend_usd"]) - finite(before["spend_usd"])
                if delta < 0:
                    raise ValueError("campaign_spend_reset_unexpected")
                report["gateway_spend"].update(after_usd=after["spend_usd"], delta_usd=str(delta))
                if delta > 0 or not report.get("inference_started"):
                    report["gateway_spend"]["status"] = (
                        "over_nominal_budget" if delta > Decimal("0.10") else "observed"
                    )
                    break
                if attempt < 5:
                    await asyncio.sleep(2)
        except Exception:
            report["gateway_spend"]["status"] = "read_failed_do_not_replay"
        # Preserve original harness report and write the supplemental metadata separately.
        path = STATE / (PLAN + ".gateway-report.json")
        with path.open("x", encoding="utf-8") as file:
            json.dump(report, file, ensure_ascii=True, allow_nan=False)
            file.flush()
            os.fsync(file.fileno())
        return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--role", choices=["admin", "smoke", "campaign-admin", "campaign"],
                        required=True)
    args = parser.parse_args()
    disabled = logging.root.manager.disable
    stage = "private_console"
    try:
        with (
            open("/dev/tty", "w", encoding="utf-8") as console,
            open("/dev/tty", encoding="utf-8") as reader,
        ):
            if not console.isatty() or not reader.isatty():
                raise ValueError("private_tty_required")
            if args.role in {"admin", "campaign-admin"}:
                stage = "admin_create_and_cleanup"
                policy = CAMPAIGN_POLICY if args.role == "campaign-admin" else SMOKE_POLICY
                return admin(console, reader, policy=policy)
            with warnings.catch_warnings():
                warnings.simplefilter("error", getpass.GetPassWarning)
                stage = "key_input"
                key = getpass.getpass("Clave " + args.role.upper() + " (entrada oculta): ",
                                     stream=console)
            logging.disable(sys.maxsize)
            sys.path.insert(0, str(ROOT))
            stage = args.role + "_execution"
            with open(os.devnull, "w") as sink, contextlib.redirect_stdout(sink), \
                    contextlib.redirect_stderr(sink):
                execute = campaign if args.role == "campaign" else smoke
                report = asyncio.run(execute(dict(os.environ), key))
            print(json.dumps(report))
            return 0 if report["status"] in {"smoke_accounting_verified", "passed"} else 1
    except (Exception, KeyboardInterrupt) as error:
        name = type(error).__name__
        print(json.dumps({"status": args.role + "_blocked_or_ambiguous", "do_not_replay": True,
                          "stage": stage, "error_class": name if name in {
                              "ValueError", "OSError", "FileExistsError", "PermissionError",
                              "ModuleNotFoundError", "KeyboardInterrupt", "HTTPStatusError",
                              "ConnectError", "ReadTimeout", "TimeoutError",
                          } else "OtherError",
                          "permission_cleanup_required": True, "campaign_approved": False}))
        return 1
    finally:
        logging.disable(disabled)


if __name__ == "__main__":
    raise SystemExit(main())
