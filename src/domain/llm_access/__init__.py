"""Governed LLM access — context, budget and usage records (specs/013 T7).

Domain layer: no Agno imports. The physical Model type is an infrastructure
detail resolved by the LLMAccess adapter in ``src/agent``.
"""

from .access import LLMAccess
from .context import current_execution_context, execution_context_scope
from .fingerprints import compute_tool_fingerprint, derive_fingerprint_key
from .models import (
    ExecutionBudget,
    ExecutionBudgetExceededError,
    ExecutionContext,
    GovernanceViolationError,
    LlmUsageEventCreate,
    generate_traceparent,
)

__all__ = [
    "ExecutionBudget",
    "ExecutionBudgetExceededError",
    "ExecutionContext",
    "GovernanceViolationError",
    "LLMAccess",
    "LlmUsageEventCreate",
    "compute_tool_fingerprint",
    "current_execution_context",
    "derive_fingerprint_key",
    "execution_context_scope",
    "generate_traceparent",
]
