"""Governed interaction runner — replaces the temporary T5 Agno adapter.

Builds the ExecutionContext from a durable interaction, binds it through a
ContextVar scope, captures the immutable config snapshot at run start and
executes one per-run Agent with an explicit ``run_id`` (specs/013 T7).

T12: when the snapshot configures cost governance, the runner first evaluates
the aggregated spend ceilings and fails closed before any Agent or inference
is created.
"""

from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime
from uuid import UUID

from agno.media import File, Image
from agno.run import RunContext
from agno.run.agent import RunOutput

from src.agent.governed_agent_factory import GovernedAgentFactory
from src.domain.interactions.media import ResolvedTelegramMedia
from src.domain.llm_access.context import execution_context_scope
from src.domain.llm_access.cost_governance import (
    LlmSpendReader,
    evaluate_cost_governance,
)
from src.domain.llm_access.models import (
    ExecutionBudget,
    ExecutionBudgetExceededError,
    ExecutionContext,
    GovernanceViolationError,
    InteractionProvenance,
    generate_traceparent,
    governance_metadata,
)
from src.domain.runtime_config.service import RuntimeConfigManager
from src.observability import (
    get_telemetry,
    log_context_scope,
    telemetry_attributes_from_execution_context,
)


class GovernedInteractionRunner:
    """Run one governed Agent execution through the T5 processor port."""

    def __init__(
        self,
        *,
        config_manager: RuntimeConfigManager,
        factory: GovernedAgentFactory,
        spend_reader: LlmSpendReader | None = None,
    ):
        self._config_manager = config_manager
        self._factory = factory
        self._spend_reader = spend_reader

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
        media: tuple[ResolvedTelegramMedia, ...] = (),
        provenance: InteractionProvenance | None = None,
    ) -> str:
        """Execute one governed non-streaming run with trusted identity.

        ``provenance`` is resolved by the processor from the admitted
        interaction; ``propose_*`` tools read it from the bound context.
        """
        snapshot = self._config_manager.snapshot()
        if snapshot.config.cost_governance is not None:
            if self._spend_reader is None:
                raise GovernanceViolationError(
                    "cost governance is configured but no spend reader is wired"
                )
            evaluate_cost_governance(
                snapshot.config,
                await self._spend_reader.summarize_spend(now=datetime.now(tz=UTC)),
            )
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
            provenance=provenance,
        )
        with execution_context_scope(context):
            observability = context.config.config.observability
            attributes = telemetry_attributes_from_execution_context(context)
            with (
                log_context_scope(attributes),
                get_telemetry().span(
                    "agno.agent.run",
                    attributes,
                    enabled=observability.traces_enabled,
                ) as span,
            ):
                run_context = RunContext(
                    run_id=run_id,
                    session_id=session_id,
                    user_id=user_id,
                    metadata=governance_metadata(context),
                )
                started = time.perf_counter()
                try:
                    images = [
                        Image(content=item.content, mime_type=item.mime_type)
                        for item in media
                        if item.is_image
                    ]
                    files = [
                        File(
                            content=item.content,
                            filename=item.filename,
                            mime_type=item.mime_type,
                        )
                        for item in media
                        if not item.is_image
                    ]
                    # Attachments are handled through the same agent.arun() call,
                    # never by invoking analyze_document directly: only arun()
                    # persists the turn into the session history, which the next
                    # turn needs to follow up on a just-ingested document (BL-1).
                    agent = self._factory.create_for_run(context)
                    agent_output: RunOutput = await asyncio.wait_for(
                        agent.arun(
                            input_text,
                            stream=False,
                            user_id=user_id,
                            session_id=session_id,
                            run_id=run_id,
                            run_context=run_context,
                            images=images or None,
                            files=files or None,
                        ),
                        timeout=context.budget.seconds_remaining(),
                    )
                    if not isinstance(agent_output.content, str):
                        raise ValueError("Governed interaction run returned non-text content")
                    return agent_output.content
                except TimeoutError as exc:
                    get_telemetry().mark_error(span, "ExecutionBudgetExceededError")
                    get_telemetry().counter(
                        "ancora.execution_budget.exceeded",
                        attributes={"ancora.budget.limit": "max_runtime_seconds"},
                        enabled=observability.metrics_enabled,
                    )
                    raise ExecutionBudgetExceededError(
                        "max_runtime_seconds",
                        "Agent run cancelled after the approved runtime budget",
                    ) from exc
                finally:
                    get_telemetry().duration_ms(
                        "ancora.agent.run.duration",
                        (time.perf_counter() - started) * 1000,
                        attributes={"ancora.status": "completed"},
                        enabled=observability.metrics_enabled,
                    )
