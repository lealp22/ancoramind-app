"""ExecutionContext, ExecutionBudget and governed usage records (specs/013 T7)."""

from __future__ import annotations

import secrets
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    from src.domain.runtime_config.models import ExecutionBudgetConfig, RuntimeConfigSnapshot


class GovernanceViolationError(RuntimeError):
    """A governed inference was attempted outside its mandatory frontier."""


class ExecutionBudgetExceededError(RuntimeError):
    """The run exceeded one of its approved execution-budget ceilings."""

    def __init__(self, limit: str, detail: str):
        super().__init__(f"Execution budget exceeded: {limit} ({detail})")
        self.limit = limit
        self.detail = detail


@dataclass
class ExecutionBudget:
    """Per-run counters and ceilings derived from an immutable config snapshot.

    Counter mutations are synchronous check-then-increment operations. Under a
    single asyncio event loop no other coroutine can interleave between the
    validation and the mutation, which keeps them safe against concurrently
    awaited tools without needing a lock.
    """

    max_runtime_seconds: int
    max_model_calls: int
    max_tool_calls: int
    max_gateway_requests: int
    max_gateway_attempts_per_model_call: int
    max_estimated_cost_usd: float | None
    started_at_monotonic: float
    model_calls: int = field(default=0, repr=False)
    gateway_requests: int = field(default=0, repr=False)

    @classmethod
    def from_config(
        cls,
        config: ExecutionBudgetConfig,
        *,
        started_at_monotonic: float,
    ) -> ExecutionBudget:
        """Build the per-run budget from the run's immutable snapshot."""
        return cls(
            max_runtime_seconds=config.max_runtime_seconds,
            max_model_calls=config.max_model_calls,
            max_tool_calls=config.max_tool_calls,
            max_gateway_requests=config.max_gateway_requests,
            max_gateway_attempts_per_model_call=config.max_gateway_attempts_per_model_call,
            max_estimated_cost_usd=config.max_estimated_cost_usd,
            started_at_monotonic=started_at_monotonic,
        )

    def seconds_remaining(self, now_monotonic: float | None = None) -> float:
        """Seconds left before the run deadline (0 when already exceeded)."""
        now = time.monotonic() if now_monotonic is None else now_monotonic
        return max(0.0, self.max_runtime_seconds - (now - self.started_at_monotonic))

    def _ensure_deadline(self) -> None:
        if self.seconds_remaining() <= 0:
            raise ExecutionBudgetExceededError("max_runtime_seconds", "run deadline reached")

    def reserve_model_call(self) -> None:
        """Reserve one logical model call plus its single Gateway request."""
        self._ensure_deadline()
        if self.model_calls >= self.max_model_calls:
            raise ExecutionBudgetExceededError("max_model_calls", "logical model-call ceiling")
        if self.gateway_requests >= self.max_gateway_requests:
            raise ExecutionBudgetExceededError("max_gateway_requests", "Gateway request ceiling")
        self.model_calls += 1
        self.gateway_requests += 1


@dataclass(frozen=True)
class ExecutionContext:
    """Trusted per-run identity, config and budget for governed inference."""

    correlation_id: UUID
    telegram_update_id: int
    agno_run_id: str
    agno_session_id: str
    config: RuntimeConfigSnapshot
    budget: ExecutionBudget
    telegram_message_id: int | None = None
    railway_request_id: str | None = None
    traceparent: str | None = None


def generate_traceparent() -> str:
    """Return a fresh W3C traceparent for runs without an upstream trace."""
    return f"00-{secrets.token_hex(16)}-{secrets.token_hex(8)}-01"


class LlmUsageEventCreate(BaseModel):
    """Durable usage record for one governed logical model call."""

    model_config = ConfigDict(frozen=True)

    interaction_id: UUID
    llm_call_id: UUID
    config_revision: int = Field(ge=0)
    logical_route: str = Field(min_length=1, max_length=127)
    effective_gateway_route: str = Field(min_length=1, max_length=127)
    provider: str = Field(default="", max_length=63)
    model: str = Field(default="", max_length=255)
    gateway_request_id: str | None = Field(default=None, max_length=255)
    provider_request_id: str | None = Field(default=None, max_length=255)
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    total_tokens: int | None = Field(default=None, ge=0)
    estimated_cost: float | None = Field(default=None, ge=0)
    cost_source: str | None = Field(default=None, max_length=31)
    latency_ms: int | None = Field(default=None, ge=0)
    time_to_first_token_ms: int | None = Field(default=None, ge=0)
    retry_count: int = Field(default=0, ge=0)
    fallback_used: bool = False
    status: str = Field(min_length=1, max_length=31)
    error_class: str | None = Field(default=None, max_length=127)
    created_at: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))

    @staticmethod
    def new_call_id() -> UUID:
        """Return the logical identifier for one model turn."""
        from uuid import uuid4

        return uuid4()


def governance_metadata(context: ExecutionContext) -> dict[str, Any]:
    """Render propagation metadata safe for RunContext and structured logs."""
    return {
        "correlation_id": str(context.correlation_id),
        "traceparent": context.traceparent,
        "config_revision": context.config.revision,
    }
