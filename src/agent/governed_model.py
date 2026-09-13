"""GovernedModel adapter — the only physical-model wrapper for governed runs.

The mixin is composed dynamically on top of the concrete provider class
(``SafeOpenRouter``/``OpenAIChat``/``OpenAILike``) so the existing OpenRouter
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

from src.domain.llm_access.context import current_execution_context
from src.domain.llm_access.models import (
    ExecutionContext,
    LlmUsageEventCreate,
)

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

    async def ainvoke(self, *args: Any, **kwargs: Any) -> Any:
        """Run one governed logical model call with budget and usage audit."""
        context = current_execution_context()
        llm_call_id = LlmUsageEventCreate.new_call_id()
        context.budget.reserve_model_call()
        started = time.perf_counter()
        try:
            # ``super()`` resolves to the concrete provider class at runtime;
            # the mixin itself has no base, hence the ignore.
            response = await super().ainvoke(*args, **kwargs)  # type: ignore[misc]
        except asyncio.CancelledError:
            # Never await audit writes while the run is being cancelled.
            raise
        except BaseException as exc:
            await self._governed_record(
                context=context,
                llm_call_id=llm_call_id,
                status="error",
                error_class=type(exc).__name__,
                latency_ms=_elapsed_ms(started),
                response=None,
            )
            raise
        await self._governed_record(
            context=context,
            llm_call_id=llm_call_id,
            status="completed",
            error_class=None,
            latency_ms=_elapsed_ms(started),
            response=response,
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
    ) -> None:
        recorder = self._governed_recorder
        if recorder is None:
            return
        provider = str(getattr(self, "provider", None) or "")
        model_id = str(getattr(self, "id", "") or "")
        event = LlmUsageEventCreate(
            interaction_id=context.correlation_id,
            llm_call_id=llm_call_id,
            config_revision=context.config.revision,
            logical_route=self._governed_route_name,
            effective_gateway_route=self._governed_effective_route,
            provider=provider,
            model=model_id,
            input_tokens=_safe_int(getattr(response, "input_tokens", None)),
            output_tokens=_safe_int(getattr(response, "output_tokens", None)),
            total_tokens=_safe_int(getattr(response, "total_tokens", None)),
            provider_request_id=_provider_request_id(response),
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
    return model


def _elapsed_ms(started: float) -> int:
    return max(0, int((time.perf_counter() - started) * 1000))


def _safe_int(value: Any) -> int | None:
    return value if isinstance(value, int) else None


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


__all__ = [
    "GovernanceStreamingOrSyncError",
    "GovernedModelMixin",
    "build_governed_model",
    "governed_model_cls",
]
