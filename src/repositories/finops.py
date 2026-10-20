"""Read-only FinOps/quality aggregates over the AncoraMind ledgers (specs/043 T2).

Every statement is a ``text()`` with bind parameters. Only ids, enums, counters,
costs and timings are selected: never ``payload_ciphertext``, ``payload`` or
``arguments_fingerprint``. Cost follows ``LlmUsageRepository.summarize_spend``:
``COALESCE(actual_cost, estimated_cost, 0)``.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.finops.models import (
    CostSourceBreakdown,
    CostTotals,
    DailyCost,
    LatencyStats,
    ProposalOutcome,
    RouteModelCost,
    StatusCount,
    UserCost,
)

_COST = "COALESCE(e.actual_cost, e.estimated_cost, 0)"
# Interactions that never ran the Agent must not count as LLM usage.
_EXCLUDED = "('rejected', 'ignored')"
_FROM = f"""
    FROM ancora.llm_usage_events e
    JOIN ancora.telegram_interactions i ON i.id = e.interaction_id
    WHERE e.created_at >= :since AND i.status NOT IN {_EXCLUDED}
"""


def _f(value: object) -> float:
    return float(value) if value is not None else 0.0  # type: ignore[arg-type]


def _i(value: object) -> int:
    return int(value) if value is not None else 0  # type: ignore[call-overload]


class FinopsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def totals(self, since: datetime) -> CostTotals:
        row = (
            await self._session.execute(
                text(f"""
                    SELECT COALESCE(SUM({_COST}), 0) AS cost,
                        COALESCE(SUM(e.input_tokens), 0) AS input_tokens,
                        COALESCE(SUM(e.output_tokens), 0) AS output_tokens,
                        COALESCE(SUM(e.total_tokens), 0) AS total_tokens,
                        COUNT(*) AS calls,
                        COUNT(*) FILTER (WHERE e.status = 'error') AS error_calls,
                        COUNT(DISTINCT e.interaction_id) AS interactions
                    {_FROM}
                """),
                {"since": since},
            )
        ).one()
        cost = _f(row.cost)
        interactions = _i(row.interactions)
        return CostTotals(
            cost_usd=cost,
            input_tokens=_i(row.input_tokens),
            output_tokens=_i(row.output_tokens),
            total_tokens=_i(row.total_tokens),
            calls=_i(row.calls),
            error_calls=_i(row.error_calls),
            interactions=interactions,
            avg_cost_per_interaction_usd=cost / interactions if interactions else 0.0,
        )

    async def daily(self, since: datetime) -> list[DailyCost]:
        rows = (
            await self._session.execute(
                text(f"""
                    SELECT (e.created_at AT TIME ZONE 'UTC')::date AS day,
                        COALESCE(SUM({_COST}), 0) AS cost,
                        COALESCE(SUM(e.total_tokens), 0) AS total_tokens,
                        COUNT(*) AS calls
                    {_FROM}
                    GROUP BY 1 ORDER BY 1
                """),
                {"since": since},
            )
        ).fetchall()
        return [
            DailyCost(
                day=r.day, cost_usd=_f(r.cost), total_tokens=_i(r.total_tokens), calls=_i(r.calls)
            )
            for r in rows
        ]

    async def by_user(self, since: datetime) -> list[tuple[str, UserCost]]:
        """Return (raw telegram user id, cost). The service pseudonymises it."""
        rows = (
            await self._session.execute(
                text(f"""
                    SELECT i.telegram_user_id AS uid,
                        COALESCE(SUM({_COST}), 0) AS cost,
                        COALESCE(SUM(e.total_tokens), 0) AS total_tokens,
                        COUNT(*) AS calls,
                        COUNT(DISTINCT e.interaction_id) AS interactions
                    {_FROM} AND i.telegram_user_id IS NOT NULL
                    GROUP BY i.telegram_user_id ORDER BY cost DESC
                """),
                {"since": since},
            )
        ).fetchall()
        return [
            (
                str(r.uid),
                UserCost(
                    user="",
                    cost_usd=_f(r.cost),
                    total_tokens=_i(r.total_tokens),
                    calls=_i(r.calls),
                    interactions=_i(r.interactions),
                ),
            )
            for r in rows
        ]

    async def by_route_model(self, since: datetime) -> list[RouteModelCost]:
        rows = (
            await self._session.execute(
                text(f"""
                    SELECT e.effective_gateway_route AS route, e.model AS model,
                        COALESCE(SUM({_COST}), 0) AS cost,
                        COALESCE(SUM(e.total_tokens), 0) AS total_tokens,
                        COUNT(*) AS calls
                    {_FROM}
                    GROUP BY e.effective_gateway_route, e.model ORDER BY cost DESC
                """),
                {"since": since},
            )
        ).fetchall()
        return [
            RouteModelCost(
                effective_gateway_route=str(r.route),
                model=r.model,
                cost_usd=_f(r.cost),
                total_tokens=_i(r.total_tokens),
                calls=_i(r.calls),
            )
            for r in rows
        ]

    async def by_cost_source(self, since: datetime) -> list[CostSourceBreakdown]:
        rows = (
            await self._session.execute(
                text(f"""
                    SELECT COALESCE(e.cost_source, 'unknown') AS source,
                        COALESCE(SUM({_COST}), 0) AS cost, COUNT(*) AS calls
                    {_FROM}
                    GROUP BY 1 ORDER BY cost DESC
                """),
                {"since": since},
            )
        ).fetchall()
        return [
            CostSourceBreakdown(cost_source=str(r.source), cost_usd=_f(r.cost), calls=_i(r.calls))
            for r in rows
        ]

    async def interactions_by_status(self, since: datetime) -> list[StatusCount]:
        rows = (
            await self._session.execute(
                text("""
                    SELECT status, COUNT(*) AS n
                    FROM ancora.telegram_interactions
                    WHERE received_at >= :since
                    GROUP BY status ORDER BY n DESC
                """),
                {"since": since},
            )
        ).fetchall()
        return [StatusCount(status=str(r.status), count=_i(r.n)) for r in rows]

    async def tool_calls_total(self, since: datetime) -> int:
        value = await self._session.scalar(
            text("""
                SELECT COALESCE(SUM(tool_call_count), 0)
                FROM ancora.telegram_interactions
                WHERE received_at >= :since
            """),
            {"since": since},
        )
        return _i(value)

    async def proposals(self, since: datetime) -> list[ProposalOutcome]:
        rows = (
            await self._session.execute(
                text("""
                    SELECT tool_name, status, consent_mode, COUNT(*) AS n
                    FROM ancora.action_proposals
                    WHERE created_at >= :since
                    GROUP BY tool_name, status, consent_mode
                    ORDER BY n DESC
                """),
                {"since": since},
            )
        ).fetchall()
        return [
            ProposalOutcome(
                tool_name=str(r.tool_name),
                status=str(r.status),
                consent_mode=str(r.consent_mode),
                count=_i(r.n),
            )
            for r in rows
        ]

    async def latency(self, since: datetime) -> LatencyStats:
        row = (
            await self._session.execute(
                text(f"""
                    SELECT
                        percentile_cont(0.5) WITHIN GROUP (ORDER BY e.latency_ms) AS p50,
                        percentile_cont(0.95) WITHIN GROUP (ORDER BY e.latency_ms) AS p95,
                        percentile_cont(0.5) WITHIN GROUP
                            (ORDER BY e.time_to_first_token_ms) AS t50,
                        percentile_cont(0.95) WITHIN GROUP
                            (ORDER BY e.time_to_first_token_ms) AS t95,
                        COUNT(*) FILTER (WHERE e.retry_count > 0) AS retried,
                        COUNT(*) FILTER (WHERE e.fallback_used) AS fallbacks
                    {_FROM} AND e.status = 'completed'
                """),
                {"since": since},
            )
        ).one()

        def opt(value: object) -> float | None:
            return float(value) if value is not None else None  # type: ignore[arg-type]

        return LatencyStats(
            p50_ms=opt(row.p50),
            p95_ms=opt(row.p95),
            ttft_p50_ms=opt(row.t50),
            ttft_p95_ms=opt(row.t95),
            retried_calls=_i(row.retried),
            fallback_calls=_i(row.fallbacks),
        )
