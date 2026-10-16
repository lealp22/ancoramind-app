"""BL-8 T7 preparation: explicit plans, Gateway-only wiring, no automatic inference."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from decimal import Decimal
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field

from src.agent.eval_physical_executor import GovernedPhysicalEvalExecutor, eval_snapshot_fingerprint
from src.agent.evals import EvalCase, load_eval_cases
from src.agent.llm_access import AgnoLLMAccess
from src.config import Settings
from src.domain.llm_access.models import LlmUsageEventCreate
from src.domain.runtime_config.models import (
    ExecutionBudgetConfig,
    RuntimeConfigSnapshot,
)


class EvalCampaignPlan(BaseModel):
    """Secret-free candidate; approval is separate and bound to its checksum."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    version: Literal[1]
    logical_route: str
    effective_gateway_route: str
    snapshot_checksum: str = Field(pattern=r"^[a-f0-9]{64}$")
    snapshot_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    config_revision: int = Field(ge=1)
    case_ids: tuple[str, ...] = Field(min_length=1, max_length=9)
    budget: ExecutionBudgetConfig
    total_estimated_cost_usd: Decimal = Field(gt=0, le=1)

    def checksum(self) -> str:
        raw = json.dumps(self.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(raw.encode()).hexdigest()

    def validate_snapshot(self, snapshot: RuntimeConfigSnapshot) -> tuple[EvalCase, ...]:
        """Pure fail-closed checks: no provider, DB, secrets, telemetry or network."""
        if (
            snapshot.source != "database"
            or snapshot.revision != self.config_revision
            or snapshot.checksum != self.snapshot_checksum
            or self.snapshot_fingerprint != eval_snapshot_fingerprint(snapshot)
        ):
            raise ValueError("eval_campaign_snapshot_mismatch")
        route = snapshot.config.routing.routes.get(self.logical_route)
        if (
            route is None
            or route.effective_gateway_route != self.effective_gateway_route
            or not {"text", "tool_calling"} <= route.capabilities
        ):
            raise ValueError("eval_campaign_route_mismatch")
        config = snapshot.config
        price = config.pricing.route_price(self.effective_gateway_route) if config.pricing else None
        if (
            price is None
            or price.input_cost_per_1m_usd is None
            or price.output_cost_per_1m_usd is None
            or config.cost_governance is None
            or self.budget.max_estimated_cost_usd is None
            or config.gateway.retries != 0
            or config.gateway.cross_model_fallbacks != 0
            or self.budget.max_gateway_attempts_per_model_call != 1
        ):
            raise ValueError("eval_campaign_pricing_or_limits_required")
        for name, value in self.budget.model_dump().items():
            ceiling = getattr(config.execution_budget, name)
            if ceiling is not None and (value is None or value > ceiling):
                raise ValueError("eval_budget_may_not_expand_snapshot")
        reserve = Decimal(str(self.budget.max_estimated_cost_usd)) * len(self.case_ids)
        if reserve > self.total_estimated_cost_usd:
            raise ValueError("eval_campaign_total_reserve_insufficient")
        if len(set(self.case_ids)) != len(self.case_ids):
            raise ValueError("eval_campaign_duplicate_cases")
        cases = {case.case_id: case for case in load_eval_cases(categories={"response_style"})}
        if any(case_id not in cases for case_id in self.case_ids):
            raise ValueError("eval_campaign_unknown_case")
        selected = tuple(cases[case_id] for case_id in self.case_ids)
        if any(case.expected_outcome != "tool_call" for case in selected):
            raise ValueError("eval_campaign_requires_tool_observable_cases")
        return selected

    def metadata(self) -> dict[str, object]:
        return {
            "plan_checksum": self.checksum(),
            "config_revision": self.config_revision,
            "snapshot_checksum": self.snapshot_checksum,
            "snapshot_fingerprint": self.snapshot_fingerprint,
            "logical_route": self.logical_route,
            "effective_gateway_route": self.effective_gateway_route,
            "case_ids": list(self.case_ids),
            "budget": self.budget.model_dump(),
            "total_estimated_cost_usd": str(self.total_estimated_cost_usd),
            "semantic_status": "not_evaluated",
        }


def gateway_settings(env: Mapping[str, str]) -> Settings:
    """Accept only explicit eval credentials and a loopback/private Railway Gateway.

    Never read .env, create a tunnel, expose a domain or resolve a direct provider.
    A loopback URL must be an operator-managed tunnel to the approved Gateway.
    """
    gateway = env.get("ANCORA_EVAL_GATEWAY_URL", "")
    key = env.get("ANCORA_EVAL_GATEWAY_KEY", "")
    parsed = urlsplit(gateway)
    host = parsed.hostname or ""
    if (
        parsed.scheme not in {"http", "https"}
        or not (host in {"localhost", "127.0.0.1", "::1"} or host.endswith(".railway.internal"))
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.path.rstrip("/") != "/v1"
    ):
        raise ValueError("eval_private_gateway_required")
    if not key.strip():
        raise ValueError("eval_gateway_key_required")
    # Bypass ambient process variables as well as .env: eval settings have no DB
    # or bot identity and cannot accidentally inherit deployment credentials.
    defaults = {
        name: field.get_default(call_default_factory=True)
        for name, field in Settings.model_fields.items()
    }
    defaults.update(
        {
            "app_env": "development",
            "_env_file": None,
            "litellm_proxy_enabled": True,
            "litellm_proxy_base_url": gateway,
            "litellm_proxy_virtual_key": key,
            "telegram_admission_enabled": False,
            "telegram_processor_enabled": False,
            "reminder_worker_enabled": False,
        }
    )
    return Settings(**defaults)


class EvalUsageRecorder:
    """In-memory metadata-only usage; no canonical interaction FK or DB writes."""

    def __init__(self) -> None:
        self.events: list[LlmUsageEventCreate] = []

    async def record(self, event: LlmUsageEventCreate) -> None:
        self.events.append(event)

    def metadata(self) -> list[dict[str, object]]:
        fields = {
            "interaction_id", "llm_call_id", "config_revision", "logical_route",
            "effective_gateway_route", "input_tokens", "output_tokens", "estimated_cost",
            "actual_cost", "cost_source", "retry_count", "fallback_used", "status", "error_class",
        }
        return [event.model_dump(mode="json", include=fields) for event in self.events]


def build_campaign_executor(
    plan: EvalCampaignPlan,
    snapshot: RuntimeConfigSnapshot,
    env: Mapping[str, str],
    recorder: EvalUsageRecorder,
) -> GovernedPhysicalEvalExecutor:
    """Wire, but never execute, the approved candidate through LLMAccess only."""
    plan.validate_snapshot(snapshot)
    if (
        env.get("ANCORA_EVAL_APPROVED_PLAN") != plan.checksum()
        or env.get("ANCORA_EVAL_SYNTHETIC_APPROVED") != "1"
        or env.get("ANCORA_EVAL_EXTERNAL_BUDGET_VERIFIED") != "1"
    ):
        raise ValueError("eval_campaign_explicit_approval_required")
    settings = gateway_settings(env)
    return GovernedPhysicalEvalExecutor(
        llm_access=AgnoLLMAccess(settings=settings, usage_recorder=recorder.record),
        snapshot=snapshot,
        budget=plan.budget,
        snapshot_fingerprint=plan.snapshot_fingerprint,
    )
