"""OpenAI-compatible governed adapter for document embeddings (specs/026)."""

from __future__ import annotations

import logging
import time
from uuid import uuid4

import httpx

from src.agent.ancora_agent import _litellm_v1_base_url
from src.config import Settings
from src.domain.documents.embeddings import DocumentEmbeddingOutcome
from src.domain.llm_access.context import current_execution_context
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
from src.observability.telemetry import get_telemetry

logger = logging.getLogger(__name__)


class GovernedDocumentEmbeddingAdapter:
    """Embed bounded document retrieval data through the approved route only."""

    ROUTE_NAME = "ancoramind-embeddings"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def embed(self, text: str) -> DocumentEmbeddingOutcome:
        """Return one vector or controlled, content-free failure metadata."""
        try:
            context = current_execution_context()
        except GovernanceViolationError:
            context = self._standalone_context()

        route = context.config.config.routing.routes.get(self.ROUTE_NAME)
        if route is None or "embeddings" not in route.capabilities:
            return DocumentEmbeddingOutcome(
                embedding=None,
                provider="",
                model="",
                status="failed",
                error_class="EmbeddingRouteUnavailable",
            )
        if self._settings.litellm_proxy_enabled:
            base_url = _litellm_v1_base_url(self._settings.litellm_proxy_base_url)
            api_key = self._settings.litellm_proxy_virtual_key
            model = route.effective_gateway_route
            provider = "litellm"
        else:
            base_url = self._settings.document_embedding_base_url or "https://api.openai.com/v1"
            api_key = self._settings.openai_api_key
            model = self._settings.document_embedding_model
            provider = self._settings.llm_provider

        if not api_key.strip():
            return DocumentEmbeddingOutcome(
                embedding=None,
                provider=provider,
                model=model,
                status="failed",
                error_class="EmbeddingCredentialsUnavailable",
            )

        started = time.perf_counter()
        headers = {"Authorization": f"Bearer {api_key}"}
        if context.traceparent:
            headers["traceparent"] = context.traceparent
        try:
            async with httpx.AsyncClient(
                timeout=self._settings.document_embedding_timeout_seconds
            ) as client:
                response = await client.post(
                    f"{base_url.rstrip('/')}/embeddings",
                    headers=headers,
                    json={
                        "model": model,
                        "input": text,
                        "dimensions": self._settings.document_embedding_dimensions,
                    },
                )
                response.raise_for_status()
                payload = response.json()
            raw_embedding = payload.get("data", [{}])[0].get("embedding")
            if (
                not isinstance(raw_embedding, list)
                or len(raw_embedding) != self._settings.document_embedding_dimensions
            ):
                raise ValueError("UnexpectedEmbeddingDimensions")
            embedding = tuple(float(value) for value in raw_embedding)
        except (httpx.HTTPError, ValueError, TypeError, IndexError, KeyError) as exc:
            error_class = type(exc).__name__
            logger.warning(
                "Document embedding failed (error_class=%s, route=%s)",
                error_class,
                self.ROUTE_NAME,
            )
            get_telemetry().counter(
                "ancora.document.embedding.calls",
                attributes={"ancora.status": "failed", "ancora.route": self.ROUTE_NAME},
            )
            return DocumentEmbeddingOutcome(None, provider, model, "failed", error_class)

        get_telemetry().counter(
            "ancora.document.embedding.calls",
            attributes={"ancora.status": "completed", "ancora.route": self.ROUTE_NAME},
        )
        get_telemetry().duration_ms(
            "ancora.document.embedding.duration",
            (time.perf_counter() - started) * 1000,
            attributes={"ancora.status": "completed"},
        )
        return DocumentEmbeddingOutcome(embedding, provider, model, "completed")

    def _standalone_context(self) -> ExecutionContext:
        config = bootstrap_runtime_configuration()
        snapshot = RuntimeConfigSnapshot(
            revision=0,
            checksum=config_checksum(config),
            source="bootstrap",
            config=config,
        )
        return ExecutionContext(
            correlation_id=uuid4(),
            telegram_update_id=0,
            agno_run_id="document-embedding-standalone",
            agno_session_id="document-embedding-standalone",
            config=snapshot,
            budget=ExecutionBudget.from_config(
                config.execution_budget,
                started_at_monotonic=time.monotonic(),
            ),
            traceparent=generate_traceparent(),
        )
