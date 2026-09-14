"""Cost-governance evaluation for governed runs (specs/013 T12).

Pure domain policy: it consumes an immutable config snapshot plus an
aggregated spend summary read from the durable usage ledger
(``ancora.llm_usage_events``) and decides whether a run may start. The ledger
is the AncoraMind spend log — it persists estimated and actual cost per call
with no content. The Gateway keeps its own operational spend/circuit state
(ADR-005); this module never depends on it.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Protocol

from src.observability import get_telemetry

if TYPE_CHECKING:
    from src.domain.runtime_config.models import RuntimeConfiguration

logger = logging.getLogger(__name__)


class CostGovernanceError(RuntimeError):
    """The approved spend ceilings block further inference (fail closed)."""

    def __init__(self, limit: str, detail: str):
        super().__init__(f"Cost governance hard stop: {limit} ({detail})")
        self.limit = limit
        self.detail = detail


@dataclass(frozen=True)
class SpendSummary:
    """Aggregated spend (USD) from the usage ledger — cost only, no content.

    ``today_usd``/``month_usd`` cover the current calendar day/month in UTC;
    ``route_month_usd`` maps each logical route to its month-to-date spend.
    """

    today_usd: float = 0.0
    month_usd: float = 0.0
    route_month_usd: Mapping[str, float] = field(default_factory=dict)


class LlmSpendReader(Protocol):
    """Port for reading the aggregated spend summary before a run starts."""

    async def summarize_spend(self, *, now: datetime) -> SpendSummary: ...


def evaluate_cost_governance(
    config: RuntimeConfiguration,
    summary: SpendSummary,
) -> None:
    """Enforce the approved spend ceilings before a governed run starts.

    Hard stops (``CostGovernanceError``): month-to-date spend reaching the
    hard-stop percentage of the external limit, or an exhausted daily, monthly
    or per-route budget. Alerts (metadata-only telemetry + warning log) at the
    60%/80% thresholds of the external limit. A config without
    ``cost_governance`` (bootstrap/free routes) enforces nothing here.

    The evaluation happens once per run; the per-call estimated-cost ceiling
    and the interaction budget bound spend while the run is in flight.
    """
    governance = config.cost_governance
    if governance is None:
        return

    external_limit = governance.external_hard_limit_usd
    month_usd = summary.month_usd
    if month_usd >= external_limit * governance.hard_stop_threshold_pct / 100:
        _hard_stop(
            "external_monthly_hard_stop",
            f"month spend {month_usd:.2f} USD reached the hard-stop threshold of the "
            f"external limit {external_limit:.2f} USD",
        )
    if month_usd >= external_limit * governance.strong_alert_threshold_pct / 100:
        _alert(governance.strong_alert_threshold_pct, month_usd, external_limit)
    elif month_usd >= external_limit * governance.alert_threshold_pct / 100:
        _alert(governance.alert_threshold_pct, month_usd, external_limit)

    if governance.daily_budget_usd is not None and summary.today_usd >= governance.daily_budget_usd:
        _hard_stop(
            "daily_budget_exhausted",
            f"today spend {summary.today_usd:.2f} USD exhausted the daily budget "
            f"{governance.daily_budget_usd:.2f} USD",
        )
    if governance.monthly_budget_usd is not None and month_usd >= governance.monthly_budget_usd:
        _hard_stop(
            "monthly_budget_exhausted",
            f"month spend {month_usd:.2f} USD exhausted the monthly budget "
            f"{governance.monthly_budget_usd:.2f} USD",
        )
    for route, budget in governance.route_monthly_budgets_usd.items():
        spent = summary.route_month_usd.get(route, 0.0)
        if spent >= budget:
            _hard_stop(
                "route_monthly_budget_exhausted",
                f"route {route} spent {spent:.2f} USD of its monthly budget {budget:.2f} USD",
            )


def _alert(threshold_pct: int, month_usd: float, external_limit: float) -> None:
    """Emit a metadata-only alert; no message content is ever included."""
    get_telemetry().counter(
        "ancora.cost_governance.alert",
        attributes={
            "ancora.cost.threshold_pct": str(threshold_pct),
            "ancora.cost.period": "month",
        },
    )
    logger.warning(
        "Cost governance alert: month spend %.2f USD reached %d%% of the external limit %.2f USD",
        month_usd,
        threshold_pct,
        external_limit,
    )


def _hard_stop(limit: str, detail: str) -> None:
    get_telemetry().counter(
        "ancora.cost_governance.hard_stop",
        attributes={"ancora.cost.limit": limit},
    )
    raise CostGovernanceError(limit, detail)


__all__ = [
    "CostGovernanceError",
    "LlmSpendReader",
    "SpendSummary",
    "evaluate_cost_governance",
]
