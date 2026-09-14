"""Async PostgreSQL persistence for governed LLM usage events (specs/013 T7)."""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.llm_access.models import LlmUsageEventCreate


class LlmUsageRepository:
    """Record one durable row per logical governed model call."""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def record(self, event: LlmUsageEventCreate) -> None:
        """Insert the usage event; correlation content is never stored."""
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
            await self._session.commit()
        except Exception:
            await self._session.rollback()
            raise
