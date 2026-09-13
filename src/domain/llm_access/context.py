"""ContextVar propagation of the ExecutionContext (specs/013 T7)."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar, Token

from src.domain.llm_access.models import ExecutionContext, GovernanceViolationError

_execution_context_var: ContextVar[ExecutionContext | None] = ContextVar(
    "ancoramind_execution_context",
    default=None,
)


def current_execution_context() -> ExecutionContext:
    """Return the active governed context or fail closed (no default context)."""
    context = _execution_context_var.get()
    if context is None:
        raise GovernanceViolationError(
            "Governed inference requires an active ExecutionContext; "
            "no model call is allowed outside a governed run scope"
        )
    return context


@contextmanager
def execution_context_scope(context: ExecutionContext) -> Iterator[ExecutionContext]:
    """Bind the context for the duration of one governed run."""
    token: Token[ExecutionContext | None] = _execution_context_var.set(context)
    try:
        yield context
    finally:
        _execution_context_var.reset(token)
