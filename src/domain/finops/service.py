"""FinOps/quality service: pseudonymisation, window validation and assembly.

Framework-independent (no Agno, no FastAPI). The repository is injected through
a Protocol so unit tests need no database (specs/043 T1).
"""

from __future__ import annotations

import hashlib
import hmac
from datetime import UTC, datetime, timedelta
from typing import Protocol

from src.domain.finops.models import (
    MAX_WINDOW_DAYS,
    MIN_WINDOW_DAYS,
    BudgetStatus,
    CostSourceBreakdown,
    CostTotals,
    DailyCost,
    FinopsReport,
    LatencyStats,
    ProposalOutcome,
    ProposalRates,
    QualityReport,
    RouteModelCost,
    StatusCount,
    UserCost,
)

_USER_DOMAIN = b"ancoramind/finops-user/v1:"
_PSEUDONYM_HEX = 8


class InvalidWindowError(ValueError):
    """The requested ``days`` window is outside the approved range."""


def validate_window(days: int) -> int:
    if isinstance(days, bool) or not MIN_WINDOW_DAYS <= days <= MAX_WINDOW_DAYS:
        raise InvalidWindowError("days_out_of_range")
    return days


def window_start(now: datetime, days: int) -> datetime:
    """UTC midnight of the oldest day: the window is ``days`` calendar days incl. today."""
    validate_window(days)
    today = now.astimezone(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    return today - timedelta(days=days - 1)


def pseudonymise_user(key: str, user_id: str) -> str:
    """Stable, non-reversible label (``u-`` + 8 hex) for a Telegram user ID."""
    digest = hmac.new(
        key.encode("utf-8"), _USER_DOMAIN + user_id.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    return "u-" + digest[:_PSEUDONYM_HEX]


class FinopsReader(Protocol):
    """Port implemented by ``FinopsRepository`` (aggregates only)."""

    async def totals(self, since: datetime) -> CostTotals: ...
    async def daily(self, since: datetime) -> list[DailyCost]: ...
    async def by_user(self, since: datetime) -> list[tuple[str, UserCost]]: ...
    async def by_route_model(self, since: datetime) -> list[RouteModelCost]: ...
    async def by_cost_source(self, since: datetime) -> list[CostSourceBreakdown]: ...
    async def interactions_by_status(self, since: datetime) -> list[StatusCount]: ...
    async def tool_calls_total(self, since: datetime) -> int: ...
    async def proposals(self, since: datetime) -> list[ProposalOutcome]: ...
    async def latency(self, since: datetime) -> LatencyStats: ...


def proposal_rates(outcomes: list[ProposalOutcome]) -> ProposalRates:
    """Rates over proposals that reached a final outcome (not pending/in flight)."""
    totals = {"executed": 0, "discarded": 0, "expired": 0}
    for outcome in outcomes:
        if outcome.status in totals:
            totals[outcome.status] += outcome.count
    resolved = sum(totals.values())

    def rate(value: int) -> float | None:
        return round(value / resolved, 4) if resolved else None

    return ProposalRates(
        resolved=resolved,
        executed=totals["executed"],
        discarded=totals["discarded"],
        expired=totals["expired"],
        executed_rate=rate(totals["executed"]),
        discarded_rate=rate(totals["discarded"]),
        expired_rate=rate(totals["expired"]),
    )


def budget_status(
    month_usd: float,
    today_usd: float,
    monthly_budget_usd: float | None,
    daily_budget_usd: float | None,
) -> BudgetStatus | None:
    if monthly_budget_usd is None and daily_budget_usd is None:
        return None

    def pct(spent: float, limit: float | None) -> float | None:
        return round(spent / limit * 100, 2) if limit else None

    return BudgetStatus(
        month_usd=month_usd,
        today_usd=today_usd,
        monthly_budget_usd=monthly_budget_usd,
        daily_budget_usd=daily_budget_usd,
        month_used_pct=pct(month_usd, monthly_budget_usd),
        day_used_pct=pct(today_usd, daily_budget_usd),
    )


class FinopsService:
    def __init__(self, reader: FinopsReader, *, pseudonym_key: str) -> None:
        if not pseudonym_key:
            raise ValueError("pseudonym_key_required")
        self._reader = reader
        self._key = pseudonym_key

    async def finops_report(
        self,
        since: datetime,
        days: int,
        *,
        budget: BudgetStatus | None = None,
    ) -> FinopsReport:
        validate_window(days)
        users = [
            user.model_copy(update={"user": pseudonymise_user(self._key, raw_id)})
            for raw_id, user in await self._reader.by_user(since)
        ]
        return FinopsReport(
            days=days,
            totals=await self._reader.totals(since),
            daily=await self._reader.daily(since),
            by_user=users,
            by_route_model=await self._reader.by_route_model(since),
            by_cost_source=await self._reader.by_cost_source(since),
            budget=budget,
        )

    async def quality_report(self, since: datetime, days: int) -> QualityReport:
        validate_window(days)
        outcomes = await self._reader.proposals(since)
        return QualityReport(
            days=days,
            interactions_by_status=await self._reader.interactions_by_status(since),
            tool_calls_total=await self._reader.tool_calls_total(since),
            proposals=outcomes,
            proposal_rates=proposal_rates(outcomes),
            latency=await self._reader.latency(since),
        )
