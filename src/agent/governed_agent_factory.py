"""Per-run Agent factory governed by the run's immutable config snapshot."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from agno.agent import Agent

from src.domain.llm_access.models import ExecutionContext

if TYPE_CHECKING:
    from src.domain.llm_access.access import LLMAccess


class GovernedAgentFactory:
    """Create one Agent per run; the snapshot is never mutated mid-run."""

    def __init__(
        self,
        *,
        llm_access: LLMAccess,
        db: Any,
        tools: list[Any],
        instructions: list[str],
    ):
        self._llm_access = llm_access
        self._db = db
        self._tools = tools
        self._instructions = instructions

    def create_for_run(
        self,
        execution_context: ExecutionContext,
        *,
        route_name: str | None = None,
    ) -> Agent:
        """Build an Agent whose model and ceilings come from the run snapshot.

        A config change activated after the run captured its snapshot only
        affects future runs (acceptance U of specs/013).
        """
        snapshot = execution_context.config
        resolved_route = route_name or snapshot.config.routing.default_route
        model = self._llm_access.model_for(resolved_route, execution_context)
        return Agent(
            id="ancoramind-governed",
            name="AncoraMind",
            model=model,
            db=self._db,
            tools=self._tools,
            tool_call_limit=snapshot.config.execution_budget.max_tool_calls,
            retries=0,
            instructions=self._instructions,
            add_history_to_context=True,
            num_history_runs=10,
            add_datetime_to_context=True,
            markdown=True,
            description=("AncoraMind — tu asistente personal inteligente con memoria operativa."),
        )
