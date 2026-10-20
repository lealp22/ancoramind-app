"""Response models for the FinOps/quality admin panel (specs/043)."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict, Field

MIN_WINDOW_DAYS = 1
MAX_WINDOW_DAYS = 90
DEFAULT_WINDOW_DAYS = 30


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True)


class CostTotals(_Frozen):
    cost_usd: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    calls: int = 0
    error_calls: int = 0
    interactions: int = 0
    avg_cost_per_interaction_usd: float = 0.0


class DailyCost(_Frozen):
    day: date
    cost_usd: float
    total_tokens: int
    calls: int


class UserCost(_Frozen):
    """Per-user spend keyed by a pseudonym, never by the Telegram ID."""

    user: str
    cost_usd: float
    total_tokens: int
    calls: int
    interactions: int


class RouteModelCost(_Frozen):
    effective_gateway_route: str
    model: str | None
    cost_usd: float
    total_tokens: int
    calls: int


class CostSourceBreakdown(_Frozen):
    cost_source: str
    cost_usd: float
    calls: int


class BudgetStatus(_Frozen):
    month_usd: float
    today_usd: float
    monthly_budget_usd: float | None = None
    daily_budget_usd: float | None = None
    month_used_pct: float | None = None
    day_used_pct: float | None = None


class FinopsReport(_Frozen):
    days: int = Field(ge=MIN_WINDOW_DAYS, le=MAX_WINDOW_DAYS)
    totals: CostTotals
    daily: list[DailyCost]
    by_user: list[UserCost]
    by_route_model: list[RouteModelCost]
    by_cost_source: list[CostSourceBreakdown]
    budget: BudgetStatus | None = None
    excluded: list[str] = Field(
        default_factory=lambda: ["dream_runs", "voice_preparations_without_usage_event"]
    )


class StatusCount(_Frozen):
    status: str
    count: int


class ProposalOutcome(_Frozen):
    tool_name: str
    status: str
    consent_mode: str
    count: int


class LatencyStats(_Frozen):
    p50_ms: float | None = None
    p95_ms: float | None = None
    ttft_p50_ms: float | None = None
    ttft_p95_ms: float | None = None
    retried_calls: int = 0
    fallback_calls: int = 0


class ProposalRates(_Frozen):
    resolved: int = 0
    executed: int = 0
    discarded: int = 0
    expired: int = 0
    executed_rate: float | None = None
    discarded_rate: float | None = None
    expired_rate: float | None = None


class QualityReport(_Frozen):
    days: int = Field(ge=MIN_WINDOW_DAYS, le=MAX_WINDOW_DAYS)
    interactions_by_status: list[StatusCount]
    tool_calls_total: int
    proposals: list[ProposalOutcome]
    proposal_rates: ProposalRates
    latency: LatencyStats
