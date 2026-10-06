"""Async PostgreSQL persistence for governed LLM usage events (specs/013 T7)."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.llm_access.cost_governance import SpendSummary
from src.domain.llm_access.models import LlmUsageEventCreate


class LlmUsageRepository:
    """Record one durable row per logical governed model call."""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def record(self, event: LlmUsageEventCreate) -> None:
        """Insert one usage event and atomically refresh its interaction summary.

        The per-call event is the detailed durable audit. ``telegram_interactions``
        keeps a metadata-only summary for operator runbooks, so both writes must
        commit or roll back together. No prompt, response, tool argument or tool
        result is involved in either statement.
        """
        try:
            await self._session.execute(
                text("""
                    INSERT INTO ancora.llm_usage_events (
                        interaction_id, llm_call_id, config_revision, logical_route,
                        effective_gateway_route, gateway_request_id, provider_request_id,
                        provider, model, input_tokens, output_tokens, total_tokens,
                        estimated_cost, actual_cost, cost_source, latency_ms,
                        time_to_first_token_ms, retry_count, fallback_used, status,
                        error_class, created_at
                    ) VALUES (
                        :interaction_id, :llm_call_id, :config_revision, :logical_route,
                        :effective_gateway_route, :gateway_request_id, :provider_request_id,
                        :provider, :model, :input_tokens, :output_tokens, :total_tokens,
                        :estimated_cost, :actual_cost, :cost_source, :latency_ms,
                        :time_to_first_token_ms, :retry_count, :fallback_used, :status,
                        :error_class, :created_at
                    )
                """),
                {
                    "interaction_id": event.interaction_id,
                    "llm_call_id": event.llm_call_id,
                    "config_revision": event.config_revision,
                    "logical_route": event.logical_route,
                    "effective_gateway_route": event.effective_gateway_route,
                    "gateway_request_id": event.gateway_request_id,
                    "provider_request_id": event.provider_request_id,
                    "provider": event.provider,
                    "model": event.model,
                    "input_tokens": event.input_tokens,
                    "output_tokens": event.output_tokens,
                    "total_tokens": event.total_tokens,
                    "estimated_cost": event.estimated_cost,
                    "actual_cost": event.actual_cost,
                    "cost_source": event.cost_source,
                    "latency_ms": event.latency_ms,
                    "time_to_first_token_ms": event.time_to_first_token_ms,
                    "retry_count": event.retry_count,
                    "fallback_used": event.fallback_used,
                    "status": event.status,
                    "error_class": event.error_class,
                    "created_at": event.created_at,
                },
            )
            await self._session.execute(
                text("""
                    UPDATE ancora.telegram_interactions
                    SET config_revision = COALESCE(config_revision, :config_revision),
                        model_call_count = model_call_count + 1,
                        gateway_request_count = gateway_request_count + 1,
                        estimated_cost = CASE
                            WHEN CAST(:estimated_cost AS NUMERIC(18, 8)) IS NULL THEN estimated_cost
                            ELSE COALESCE(estimated_cost, 0)
                                + CAST(:estimated_cost AS NUMERIC(18, 8))
                        END,
                        actual_cost = CASE
                            WHEN CAST(:actual_cost AS NUMERIC(18, 8)) IS NULL THEN actual_cost
                            ELSE COALESCE(actual_cost, 0)
                                + CAST(:actual_cost AS NUMERIC(18, 8))
                        END,
                        updated_at = :updated_at
                    WHERE id = :interaction_id
                """),
                {
                    "interaction_id": event.interaction_id,
                    "config_revision": event.config_revision,
                    "estimated_cost": event.estimated_cost,
                    "actual_cost": event.actual_cost,
                    "updated_at": event.created_at,
                },
            )
            await self._session.commit()
        except Exception:
            await self._session.rollback()
            raise

    async def finish_speech_call(
        self, interaction_id: UUID, call_id: UUID, *, status: str, latency_ms: int
    ) -> None:
        """Settle an existing intent without incrementing interaction counters twice."""
        await self._session.execute(
            text("""
            UPDATE ancora.llm_usage_events SET status = :status, latency_ms = :latency,
                error_class = CASE WHEN :status = 'completed' THEN NULL
                    ELSE 'SpeechGatewayError' END
            WHERE interaction_id = :interaction AND llm_call_id = :call AND status = 'started'
        """),
            {
                "interaction": interaction_id,
                "call": call_id,
                "status": status,
                "latency": latency_ms,
            },
        )
        await self._session.commit()

    async def summarize_spend(self, *, now: datetime | None = None) -> SpendSummary:
        """Aggregate the AncoraMind spend log for cost governance (T12).

        Actual cost (provider-reported) takes precedence over the estimate;
        the query never touches message or argument content. Day and month
        boundaries are calendar-based in UTC.
        """
        reference = datetime.now(tz=UTC) if now is None else now.astimezone(UTC)
        day_start = reference.replace(hour=0, minute=0, second=0, microsecond=0)
        month_start = day_start.replace(day=1)
        rows = (
            await self._session.execute(
                text("""
                    SELECT
                        logical_route,
                        COALESCE(SUM(COALESCE(actual_cost, estimated_cost, 0)), 0) AS month_usd,
                        COALESCE(
                            SUM(COALESCE(actual_cost, estimated_cost, 0))
                                FILTER (WHERE created_at >= :day_start),
                            0
                        ) AS today_usd
                    FROM (
                        SELECT logical_route, actual_cost, estimated_cost, created_at
                        FROM ancora.llm_usage_events
                        UNION ALL
                        SELECT logical_route, actual_cost, estimated_cost, claimed_at AS created_at
                        FROM ancora.voice_preparations v
                        WHERE call_id IS NOT NULL AND NOT EXISTS (
                            SELECT 1 FROM ancora.llm_usage_events e WHERE e.llm_call_id = v.call_id
                        )
                    ) AS spend
                    WHERE created_at >= :month_start
                    GROUP BY logical_route
                """),
                {"day_start": day_start, "month_start": month_start},
            )
        ).fetchall()
        route_month = {
            str(row.logical_route): float(row.month_usd) for row in rows if row.month_usd
        }
        return SpendSummary(
            today_usd=sum(float(row.today_usd or 0) for row in rows),
            month_usd=sum(route_month.values()),
            route_month_usd=route_month,
        )
