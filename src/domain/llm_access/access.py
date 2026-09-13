"""LLMAccess port — the only frontier allowed to produce inference models."""

from __future__ import annotations

from typing import Any, Protocol

from src.domain.llm_access.models import ExecutionContext


class LLMAccess(Protocol):
    """Resolve a governed model for a logical route and an execution context.

    Implementations must fail closed when the route is unknown or the context
    is missing, and must never expose physical provider secrets to callers.
    The returned object is a physical model instance; its concrete type is an
    infrastructure detail (Agno ``Model`` today) and is therefore opaque to
    the domain layer.
    """

    def model_for(self, route_name: str, execution_context: ExecutionContext) -> Any: ...
