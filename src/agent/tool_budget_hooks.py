"""Agno tool hook enforcing the per-run execution budget (specs/013 T8).

The hook is asynchronous because governed runs use ``Agent.arun()`` and Agno
2.9.0 awaits async hooks on that path. This means success is counted only after
an async tool itself has completed. A budget rejection is converted to Agno's
``StopAgentRun`` so the current Agent loop terminates without another model turn.
Agno's ``tool_call_limit`` remains an independent hard ceiling.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import Any

from agno.exceptions import StopAgentRun

from src.domain.llm_access.context import current_execution_context
from src.domain.llm_access.fingerprints import compute_tool_fingerprint
from src.domain.llm_access.models import ExecutionBudgetExceededError


def build_budget_tool_hook(fingerprint_key: str) -> Callable[..., Any]:
    """Build the async tool hook for one governed run factory."""

    async def execution_budget_tool_hook(
        name: str,
        func: Callable[..., Any],
        args: dict[str, Any],
    ) -> Any:
        """Wrap one tool execution with budget reservation and fingerprinting."""
        context = current_execution_context()
        budget = context.budget
        fingerprint = compute_tool_fingerprint(fingerprint_key, name, args)
        try:
            budget.reserve_tool_call(fingerprint)
        except ExecutionBudgetExceededError as exc:
            raise StopAgentRun(str(exc)) from exc
        try:
            result = func(**args)
            if inspect.isawaitable(result):
                result = await result
        except Exception:
            budget.record_tool_failure(fingerprint)
            raise
        budget.record_tool_success(fingerprint)
        return result

    return execution_budget_tool_hook


__all__ = ["ExecutionBudgetExceededError", "build_budget_tool_hook"]
