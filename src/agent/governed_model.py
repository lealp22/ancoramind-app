"""GovernedModel adapter — the only physical-model wrapper for governed runs.

The mixin is composed dynamically on top of the concrete provider class
(``SafeOpenRouter``/``OpenAIChat``/``SafeOpenAILike``) so the shared provider
safety fixes (malformed tool calls, stream-loop termination) are preserved
instead of being replaced. Agno's agentic loop is not reimplemented: the
mixin only intercepts the per-turn ``ainvoke`` primitive that ``aresponse``
already wraps (specs/013 T7).
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any, cast

from agno.models.base import Model

from src.domain.emergency_stop.models import EmergencyStopActiveError
from src.domain.emergency_stop.ports import EmergencyStopReader
from src.domain.llm_access.context import current_execution_context
from src.domain.llm_access.models import (
    ExecutionBudgetExceededError,
    ExecutionContext,
    LlmUsageEventCreate,
)
from src.observability import get_telemetry, telemetry_attributes_from_execution_context

logger = logging.getLogger(__name__)

UsageRecorder = Callable[[LlmUsageEventCreate], Awaitable[None]]


class GovernanceStreamingOrSyncError(RuntimeError):
    """A governed model was driven through a disabled sync/streaming path."""


class GovernedModelMixin:
    """Fail-closed governance applied to every logical model call.

    Attributes are attached after construction (dataclass base ``__init__``
    signatures stay untouched) by :func:`build_governed_model`.
    """

    _governed_recorder: UsageRecorder | None
    _governed_route_name: str
    _governed_effective_route: str
    _governed_revision: int
    _governed_provider_label: str | None
    _governed_stop_reader: EmergencyStopReader | None

    async def ainvoke(self, *args: Any, **kwargs: Any) -> Any:
        """Run one governed logical model call with budget and usage audit."""
        context = current_execution_context()
        stop_reader = self._governed_stop_reader
        if stop_reader is not None:
            stop_state = stop_reader.current()
            if stop_state.active:
                get_telemetry().counter(
                    "ancora.emergency_stop.blocked",
                    attributes={"ancora.route": self._governed_route_name},
                )
                raise EmergencyStopActiveError(stop_state.reason)
        llm_call_id = LlmUsageEventCreate.new_call_id()
        estimated_cost = _estimate_call_cost(context, self._governed_effective_route, args, kwargs)
        observability = context.config.config.observability
        attributes = {
            **telemetry_attributes_from_execution_context(context),
            "ancora.route": self._governed_route_name,
            "ancora.effective_route": self._governed_effective_route,
            "gen_ai.provider.name": self._governed_provider_label
            or str(getattr(self, "provider", "") or ""),
            "gen_ai.request.model": str(getattr(self, "id", "") or ""),
        }
        try:
            context.budget.reserve_model_call(estimated_cost)
        except ExecutionBudgetExceededError as exc:
            get_telemetry().counter(
                "ancora.execution_budget.exceeded",
                attributes={"ancora.budget.limit": exc.limit},
                enabled=observability.metrics_enabled,
            )
            raise
        started = time.perf_counter()
        with get_telemetry().span(
            "gen_ai.model.call",
            attributes,
            enabled=observability.traces_enabled,
        ) as span:
            try:
                # ``super()`` resolves to the concrete provider class at runtime;
                # the mixin itself has no base, hence the ignore.
                response = await super().ainvoke(*args, **kwargs)  # type: ignore[misc]
            except asyncio.CancelledError:
                # Never await audit writes while the run is being cancelled.
                raise
            except BaseException as exc:
                get_telemetry().mark_error(span, type(exc).__name__)
                await self._governed_record(
                    context=context,
                    llm_call_id=llm_call_id,
                    status="error",
                    error_class=type(exc).__name__,
                    latency_ms=_elapsed_ms(started),
                    response=None,
                    estimated_cost=estimated_cost or None,
                )
                get_telemetry().counter(
                    "ancora.llm.calls",
                    attributes={
                        **attributes,
                        "ancora.status": "error",
                        "error.type": type(exc).__name__,
                    },
                    enabled=observability.metrics_enabled,
                )
                raise
            actual_cost = _actual_call_cost(context, self._governed_effective_route, response)
            span_attributes = {
                "gen_ai.usage.input_tokens": _usage_tokens(response, "input_tokens"),
                "gen_ai.usage.output_tokens": _usage_tokens(response, "output_tokens"),
                "gen_ai.usage.total_tokens": _usage_tokens(response, "total_tokens"),
                "gen_ai.usage.estimated_cost_usd": estimated_cost or None,
                "gen_ai.usage.actual_cost_usd": actual_cost,
            }
            for key, value in span_attributes.items():
                if value is not None:
                    span.set_attribute(key, value)
        context.budget.settle_actual_cost(actual_cost)
        await self._governed_record(
            context=context,
            llm_call_id=llm_call_id,
            status="completed",
            error_class=None,
            latency_ms=_elapsed_ms(started),
            response=response,
            estimated_cost=estimated_cost or None,
            actual_cost=actual_cost,
        )
        metric_attributes = {**attributes, "ancora.status": "completed"}
        get_telemetry().counter(
            "ancora.llm.calls",
            attributes=metric_attributes,
            enabled=observability.metrics_enabled,
        )
        get_telemetry().duration_ms(
            "ancora.llm.call.duration",
            _elapsed_ms(started),
            attributes=metric_attributes,
            enabled=observability.metrics_enabled,
        )
        for metric_name, value in (
            ("ancora.llm.input_tokens", _usage_tokens(response, "input_tokens")),
            ("ancora.llm.output_tokens", _usage_tokens(response, "output_tokens")),
            ("ancora.llm.total_tokens", _usage_tokens(response, "total_tokens")),
        ):
            if value is not None:
                get_telemetry().counter(
                    metric_name,
                    value,
                    attributes=metric_attributes,
                    enabled=observability.metrics_enabled,
                )
        if estimated_cost > 0:
            get_telemetry().counter(
                "ancora.llm.estimated_cost_usd",
                estimated_cost,
                attributes=metric_attributes,
                enabled=observability.metrics_enabled,
            )
        if actual_cost is not None:
            get_telemetry().counter(
                "ancora.llm.actual_cost_usd",
                actual_cost,
                attributes=metric_attributes,
                enabled=observability.metrics_enabled,
            )
        return response

    def invoke(self, *args: Any, **kwargs: Any) -> Any:
        """Reject synchronous inference: governed runs are async-only."""
        raise GovernanceStreamingOrSyncError(
            "Synchronous model invocation is not allowed for governed models"
        )

    def invoke_stream(self, *args: Any, **kwargs: Any) -> Any:
        """Reject streaming: visible Telegram streaming is disabled initially."""
        raise GovernanceStreamingOrSyncError(
            "Streaming is not allowed for governed models in this phase (specs/013 §8)"
        )

    async def ainvoke_stream(self, *args: Any, **kwargs: Any) -> Any:
        """Reject streaming: visible Telegram streaming is disabled initially."""
        raise GovernanceStreamingOrSyncError(
            "Streaming is not allowed for governed models in this phase (specs/013 §8)"
        )

    async def _governed_record(
        self,
        *,
        context: ExecutionContext,
        llm_call_id: Any,
        status: str,
        error_class: str | None,
        latency_ms: int,
        response: Any,
        estimated_cost: float | None = None,
        actual_cost: float | None = None,
    ) -> None:
        recorder = self._governed_recorder
        if recorder is None:
            return
        provider = self._governed_provider_label or str(getattr(self, "provider", None) or "")
        model_id = str(getattr(self, "id", "") or "")
        cost_source = "pricing_snapshot" if (estimated_cost or actual_cost) else None
        event = LlmUsageEventCreate(
            interaction_id=context.correlation_id,
            llm_call_id=llm_call_id,
            config_revision=context.config.revision,
            logical_route=self._governed_route_name,
            effective_gateway_route=self._governed_effective_route,
            provider=provider,
            model=model_id,
            input_tokens=_usage_tokens(response, "input_tokens"),
            output_tokens=_usage_tokens(response, "output_tokens"),
            total_tokens=_usage_tokens(response, "total_tokens"),
            provider_request_id=_provider_request_id(response),
            estimated_cost=estimated_cost,
            actual_cost=actual_cost,
            cost_source=cost_source,
            latency_ms=latency_ms,
            time_to_first_token_ms=_duration_ms(getattr(response, "time_to_first_token", None)),
            status=status,
            error_class=error_class,
        )
        try:
            await recorder(event)
        except Exception:
            # Audit writes are fail-open: a telemetry/audit outage must never
            # fail an inference the budget already approved (ADR-006 spirit).
            logger.warning(
                "Governed LLM usage audit write failed (llm_call_id=%s, status=%s)",
                llm_call_id,
                status,
                exc_info=True,
            )


_GOVERNED_CLASSES: dict[type, type] = {}


def governed_model_cls[T: Model](base_cls: type[T]) -> type[T]:
    """Return (and cache) the governed subclass of a concrete provider class."""
    governed = _GOVERNED_CLASSES.get(base_cls)
    if governed is None:
        governed = type(
            f"Governed{base_cls.__name__}",
            (GovernedModelMixin, base_cls),
            {"__doc__": f"Governed adapter composed on {base_cls.__name__}."},
        )
        _GOVERNED_CLASSES[base_cls] = governed
    return governed


def build_governed_model[T: Model](
    base_cls: type[T],
    kwargs: dict[str, Any],
    *,
    recorder: UsageRecorder | None,
    route_name: str,
    effective_route: str,
    revision: int,
    provider_label: str | None = None,
    stop_reader: EmergencyStopReader | None = None,
) -> T:
    """Instantiate the governed model and attach its governance state.

    ``retries`` is always forced to the approved policy of 0 regardless of
    what the caller passed, so governed models can never self-retry.
    """
    constructor_kwargs = {key: value for key, value in kwargs.items() if key != "retries"}
    model = governed_model_cls(base_cls)(retries=0, **constructor_kwargs)
    governed = cast(GovernedModelMixin, model)
    governed._governed_recorder = recorder
    governed._governed_route_name = route_name
    governed._governed_effective_route = effective_route
    governed._governed_revision = revision
    governed._governed_provider_label = provider_label
    governed._governed_stop_reader = stop_reader
    return model


def _elapsed_ms(started: float) -> int:
    return max(0, int((time.perf_counter() - started) * 1000))


def _safe_int(value: Any) -> int | None:
    return value if isinstance(value, int) else None


def _usage_tokens(response: Any, name: str) -> int | None:
    """Read token usage from a provider response.

    Agno's chat adapters (``OpenAIChat``/``OpenRouter``/``OpenAILike``) do not set
    ``ModelResponse.input_tokens``; they report usage in ``response_usage`` (a
    ``MessageMetrics``). Prefer the direct attribute so other adapters keep working.
    """
    direct = _safe_int(getattr(response, name, None))
    if direct is not None:
        return direct
    return _safe_int(getattr(getattr(response, "response_usage", None), name, None))


def _duration_ms(value: Any) -> int | None:
    """Normalize Agno's integer-ms or float-second timing value to milliseconds."""
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value >= 0:
        return int(value * 1000)
    return None


def _provider_request_id(response: Any) -> str | None:
    provider_data = getattr(response, "provider_data", None)
    if isinstance(provider_data, dict):
        request_id = provider_data.get("id")
        if isinstance(request_id, str) and request_id:
            return request_id[:255]
    return None


_APPROX_CHARS_PER_TOKEN = 4


def _messages_char_count(args: tuple[Any, ...], kwargs: dict[str, Any]) -> int:
    """Approximate prompt size by summing message content lengths."""
    for candidate in (*args, *kwargs.values()):
        if not isinstance(candidate, list) or not candidate:
            continue
        first = candidate[0]
        if hasattr(first, "content"):
            return sum(len(str(getattr(item, "content", None) or "")) for item in candidate)
        if isinstance(first, dict) and "content" in first:
            return sum(len(str(item.get("content") or "")) for item in candidate)
    return 0


def _estimate_call_cost(
    context: ExecutionContext,
    effective_route: str,
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
) -> float:
    """Estimate the call cost from the snapshot pricing (no I/O on this path)."""
    pricing = context.config.config.pricing
    if pricing is None:
        return 0.0
    price = pricing.route_price(effective_route)
    if price is None:
        return 0.0
    budget_config = context.config.config.execution_budget
    cost = 0.0
    if price.input_cost_per_1m_usd is not None:
        input_tokens = max(1, _messages_char_count(args, kwargs) // _APPROX_CHARS_PER_TOKEN)
        cost += input_tokens * price.input_cost_per_1m_usd / 1_000_000
    if price.output_cost_per_1m_usd is not None:
        cost += budget_config.max_output_tokens * price.output_cost_per_1m_usd / 1_000_000
    return cost


def _actual_call_cost(
    context: ExecutionContext,
    effective_route: str,
    response: Any,
) -> float | None:
    """Reconcile actual cost from provider usage when pricing is configured."""
    pricing = context.config.config.pricing
    if pricing is None:
        return None
    price = pricing.route_price(effective_route)
    if price is None:
        return None
    cost = 0.0
    seen = False
    input_tokens = _usage_tokens(response, "input_tokens")
    output_tokens = _usage_tokens(response, "output_tokens")
    if input_tokens is not None and price.input_cost_per_1m_usd is not None:
        cost += input_tokens * price.input_cost_per_1m_usd / 1_000_000
        seen = True
    if output_tokens is not None and price.output_cost_per_1m_usd is not None:
        cost += output_tokens * price.output_cost_per_1m_usd / 1_000_000
        seen = True
    return cost if seen else None


__all__ = [
    "GovernanceStreamingOrSyncError",
    "GovernedModelMixin",
    "build_governed_model",
    "governed_model_cls",
]
