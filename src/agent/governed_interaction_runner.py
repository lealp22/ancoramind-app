"""Governed interaction runner — replaces the temporary T5 Agno adapter.

Builds the ExecutionContext from a durable interaction, binds it through a
ContextVar scope, captures the immutable config snapshot at run start and
executes one per-run Agent with an explicit ``run_id`` (specs/013 T7).
"""

from __future__ import annotations

import time
from uuid import UUID

from agno.run import RunContext

from src.agent.governed_agent_factory import GovernedAgentFactory
from src.domain.llm_access.context import execution_context_scope
from src.domain.llm_access.models import (
    ExecutionBudget,
    ExecutionContext,
    generate_traceparent,
    governance_metadata,
)
from src.domain.runtime_config.service import RuntimeConfigManager


class GovernedInteractionRunner:
    """Run one governed Agent execution through the T5 processor port."""

    def __init__(self, *, config_manager: RuntimeConfigManager, factory: GovernedAgentFactory):
        self._config_manager = config_manager
        self._factory = factory

    async def run(
        self,
        input_text: str,
        *,
        user_id: str,
        session_id: str,
        run_id: str,
        correlation_id: UUID,
        telegram_update_id: int,
        telegram_message_id: int | None = None,
    ) -> str:
        """Execute one governed non-streaming run with trusted identity."""
        snapshot = self._config_manager.snapshot()
        context = ExecutionContext(
            correlation_id=correlation_id,
            telegram_update_id=telegram_update_id,
            telegram_message_id=telegram_message_id,
            railway_request_id=None,
            agno_run_id=run_id,
            agno_session_id=session_id,
            config=snapshot,
            budget=ExecutionBudget.from_config(
                snapshot.config.execution_budget,
                started_at_monotonic=time.monotonic(),
            ),
            traceparent=generate_traceparent(),
        )
        with execution_context_scope(context):
            agent = self._factory.create_for_run(context)
            run_context = RunContext(
                run_id=run_id,
                session_id=session_id,
                user_id=user_id,
                metadata=governance_metadata(context),
            )
            output = await agent.arun(
                input_text,
                stream=False,
                user_id=user_id,
                session_id=session_id,
                run_id=run_id,
                run_context=run_context,
            )
        if not isinstance(output.content, str):
            raise ValueError("Governed interaction run returned non-text content")
        return output.content
