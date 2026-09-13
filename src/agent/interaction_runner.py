"""Temporary Agno adapter for T5 interaction processing.

T7 will replace this adapter with governed LLM access and an Agent created per
run. Keeping the dependency here prevents the domain processor from importing
Agno directly.
"""

from __future__ import annotations

from uuid import UUID

from agno.agent import Agent
from agno.run import RunContext


class AgnoInteractionRunner:
    """Run the current AncoraMind Agent through the T5 processor port."""

    def __init__(self, agent: Agent):
        self._agent = agent

    async def run(
        self,
        input_text: str,
        *,
        user_id: str,
        session_id: str,
        run_id: str,
        correlation_id: UUID,
    ) -> str:
        """Execute one non-streaming Agent run with trusted channel identity."""
        run_context = RunContext(
            run_id=run_id,
            session_id=session_id,
            user_id=user_id,
            metadata={"correlation_id": str(correlation_id)},
        )
        output = await self._agent.arun(
            input_text,
            stream=False,
            user_id=user_id,
            session_id=session_id,
            run_id=run_id,
            run_context=run_context,
        )
        if not isinstance(output.content, str):
            raise ValueError("Agno interaction run returned non-text content")
        return output.content
