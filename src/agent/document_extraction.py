"""Agno adapter for the ``DocumentExtractionPort`` (specs/013 T9).

All extraction inference is resolved through LLMAccess. When the call happens
inside a governed run (T5/T7 processor) the run's ``ExecutionContext`` is
reused, so the extraction shares its config snapshot, execution budget, cost
accounting and trace, and its usage event is audited under the interaction.

On the transitional AgentOS webhook path there is no governed run. The adapter
builds a standalone bootstrap-scoped context (own budget and trace) through a
separate unaudited LLMAccess: there is no interaction row to reference, so no
``llm_usage_events`` row is written; the durable extraction audit remains
``ancora.ai_extractions`` with the real provider/model.
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from agno.agent import Agent
from agno.media import Image
from pydantic import BaseModel

from src.agent.instructions import load_prompt
from src.domain.documents.extraction import DocumentExtractionOutcome, DocumentVisualPage
from src.domain.llm_access.context import current_execution_context, execution_context_scope
from src.domain.llm_access.models import (
    ExecutionBudget,
    ExecutionContext,
    GovernanceViolationError,
    generate_traceparent,
)
from src.domain.runtime_config.models import (
    RuntimeConfigSnapshot,
    bootstrap_runtime_configuration,
    config_checksum,
)
from src.observability import get_telemetry, telemetry_attributes_from_execution_context

if TYPE_CHECKING:
    from src.domain.llm_access.access import LLMAccess

logger = logging.getLogger(__name__)

class AgnoDocumentExtractionAdapter:
    """Extract structured document data through the governed LLMAccess frontier."""

    def __init__(
        self,
        *,
        llm_access: LLMAccess,
        standalone_llm_access: LLMAccess | None = None,
        route_name: str = "ancoramind-default",
        vision_route_name: str = "ancoramind-vision",
    ) -> None:
        self._llm_access = llm_access
        self._standalone_llm_access = standalone_llm_access
        self._route_name = route_name
        self._vision_route_name = vision_route_name

    async def extract[TSchema: BaseModel](
        self,
        prompt: str,
        schema: type[TSchema],
        visual_pages: tuple[DocumentVisualPage, ...] = (),
    ) -> DocumentExtractionOutcome[TSchema]:
        """Run one governed structured extraction call."""
        try:
            context = current_execution_context()
        except GovernanceViolationError:
            context = None
        route_name = self._vision_route_name if visual_pages else self._route_name
        if context is not None:
            model = self._llm_access.model_for(route_name, context)
            return await self._run_extraction_agent(model, prompt, schema, visual_pages, route_name)
        return await self._extract_standalone(prompt, schema, visual_pages, route_name)

    async def _extract_standalone[TSchema: BaseModel](
        self,
        prompt: str,
        schema: type[TSchema],
        visual_pages: tuple[DocumentVisualPage, ...],
        route_name: str,
    ) -> DocumentExtractionOutcome[TSchema]:
        """Governed fallback for the transitional path without a run context."""
        if self._standalone_llm_access is None:
            raise GovernanceViolationError(
                "Document extraction requires a governed run or a standalone "
                "governed frontier; no direct model call is allowed"
            )
        config = bootstrap_runtime_configuration()
        context = ExecutionContext(
            correlation_id=uuid4(),
            telegram_update_id=0,
            agno_run_id="document-extraction-standalone",
            agno_session_id="document-extraction",
            config=RuntimeConfigSnapshot(
                revision=0,
                checksum=config_checksum(config),
                source="bootstrap",
                config=config,
            ),
            budget=ExecutionBudget.from_config(
                config.execution_budget,
                started_at_monotonic=time.monotonic(),
            ),
            traceparent=generate_traceparent(),
        )
        logger.warning(
            "Document extraction running on the transitional standalone governed "
            "context (no interaction row; usage events are not recorded)"
        )
        with execution_context_scope(context):
            model = self._standalone_llm_access.model_for(route_name, context)
            return await self._run_extraction_agent(model, prompt, schema, visual_pages, route_name)

    async def _run_extraction_agent[TSchema: BaseModel](
        self,
        model: Any,
        prompt: str,
        schema: type[TSchema],
        visual_pages: tuple[DocumentVisualPage, ...],
        route_name: str,
    ) -> DocumentExtractionOutcome[TSchema]:
        """Run one structured-output Agno Agent turn over the governed model."""
        provider = str(getattr(model, "provider", None) or "")
        model_id = str(getattr(model, "id", None) or "")
        context = current_execution_context()
        observability = context.config.config.observability
        attributes = {
            **telemetry_attributes_from_execution_context(context),
            "ancora.route": route_name,
            "gen_ai.provider.name": provider,
            "gen_ai.request.model": model_id,
        }
        agent = Agent(
            model=model,
            output_schema=schema,
            instructions=[load_prompt("skills/document_extraction.md")],
            markdown=False,
            retries=0,
            telemetry=False,
        )
        with get_telemetry().span(
            "agno.agent.run",
            attributes,
            enabled=observability.traces_enabled,
        ) as span:
            try:
                response = await agent.arun(
                    prompt,
                    images=[
                        Image(content=page.content, mime_type=page.mime_type)
                        for page in visual_pages
                    ]
                    or None,
                )
            except Exception as exc:
                get_telemetry().mark_error(span, type(exc).__name__)
                # Bounded, content-free failure metadata (specs/013 T9): the
                # inference error class is observable instead of silently ignored.
                logger.warning(
                    "Document extraction inference failed (error_class=%s, provider=%s, model=%s)",
                    type(exc).__name__,
                    provider,
                    model_id,
                )
                return DocumentExtractionOutcome(
                    extraction=None,
                    provider=provider,
                    model=model_id,
                    status="failed",
                    error_class=type(exc).__name__,
                )
            run_status = getattr(response, "status", None)
            if str(getattr(run_status, "value", run_status)).upper() == "ERROR":
                get_telemetry().mark_error(span, "AgentRunError")
                # Agno absorbs model errors into RunOutput(status=error) and places
                # the exception text in content; only the bounded class marker is
                # surfaced, never the message (it may embed provider payloads).
                logger.warning(
                    "Document extraction agent run errored (provider=%s, model=%s)",
                    provider,
                    model_id,
                )
                return DocumentExtractionOutcome(
                    extraction=None,
                    provider=provider,
                    model=model_id,
                    status="failed",
                    error_class="AgentRunError",
                )
        content = getattr(response, "content", None)
        extraction = _coerce_content(content, schema)
        if extraction is None:
            return DocumentExtractionOutcome(
                extraction=None,
                provider=provider,
                model=model_id,
                status="failed",
                error_class="InvalidExtractionContent",
            )
        return DocumentExtractionOutcome(
            extraction=extraction,
            provider=provider,
            model=model_id,
            status="completed",
        )


def _coerce_content[TSchema: BaseModel](content: Any, schema: type[TSchema]) -> TSchema | None:
    """Convert the agent's structured output into the requested schema."""
    if isinstance(content, schema):
        return content
    if isinstance(content, dict):
        try:
            return schema(**content)
        except Exception:
            return None
    if isinstance(content, str) and content.strip():
        try:
            return schema.model_validate_json(content)
        except Exception:
            return None
    return None


__all__ = ["AgnoDocumentExtractionAdapter"]
