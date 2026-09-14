"""LLMAccess implementation and durable usage recording (specs/013 T7).

Physical provider resolution is transitional: until the LiteLLM Gateway lands
(T10), governed runs call OpenRouter/provider directly, but only through this
frontier, with budget enforcement, per-call audit and fail-closed semantics.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.agent.ancora_agent import resolve_model_parts
from src.agent.governed_model import UsageRecorder, build_governed_model
from src.config import Settings
from src.domain.llm_access.models import (
    ExecutionContext,
    GovernanceViolationError,
    LlmUsageEventCreate,
)
from src.repositories.llm_usage import LlmUsageRepository

if TYPE_CHECKING:
    from agno.models.base import Model

logger = logging.getLogger(__name__)

SessionFactory = Callable[[], Awaitable[AsyncSession]]


class LlmUsageRecorder:
    """Persist one usage row per governed call; audit writes are fail-open."""

    def __init__(self, session_factory: SessionFactory):
        self._session_factory = session_factory

    async def record(self, event: LlmUsageEventCreate) -> None:
        session: AsyncSession | None = None
        try:
            session = await self._session_factory()
            await LlmUsageRepository(session).record(event)
        except Exception:
            logger.warning(
                "LLM usage event could not be persisted (llm_call_id=%s)",
                event.llm_call_id,
                exc_info=True,
            )
        finally:
            if session is not None:
                try:
                    await session.close()
                except SQLAlchemyError:  # pragma: no cover - close rarely fails
                    logger.warning("LLM usage session close failed", exc_info=True)


class AgnoLLMAccess:
    """The only frontier allowed to create inference models for governed runs."""

    def __init__(self, *, settings: Settings, usage_recorder: UsageRecorder | None):
        self._settings = settings
        self._usage_recorder = usage_recorder

    def model_for(self, route_name: str, execution_context: ExecutionContext) -> Model:
        """Return a governed model bound to the run's snapshot and context.

        Fails closed when the route is unknown in the run's immutable snapshot.
        """
        snapshot = execution_context.config
        route = snapshot.config.routing.routes.get(route_name)
        if route is None:
            raise GovernanceViolationError(
                f"Logical route {route_name!r} is not defined in the active "
                f"runtime configuration (revision {snapshot.revision})"
            )
        base_cls, kwargs = resolve_model_parts(
            provider=self._settings.llm_provider,
            model_id=self._settings.llm_model,
            base_url=self._settings.llm_base_url,
            api_key=self._resolve_api_key(),
        )
        if execution_context.traceparent:
            headers = dict(kwargs.get("extra_headers") or {})
            headers["traceparent"] = execution_context.traceparent
            kwargs["extra_headers"] = headers
        return build_governed_model(
            base_cls,
            kwargs,
            recorder=self._usage_recorder,
            route_name=route_name,
            effective_route=route.effective_gateway_route,
            revision=snapshot.revision,
        )

    def _resolve_api_key(self) -> str | None:
        if self._settings.llm_provider == "openrouter" and self._settings.openrouter_api_key:
            return self._settings.openrouter_api_key
        if (
            self._settings.llm_provider in ("openai", "openai-like")
            and self._settings.openai_api_key
        ):
            return self._settings.openai_api_key
        return None
