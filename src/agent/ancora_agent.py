"""AncoraMind Agent — Agno agent creation and LLM model factory.

Supports multiple LLM providers:
- openai:     OpenAIChat (uses OPENAI_API_KEY)
- openrouter: OpenRouter (uses OPENROUTER_API_KEY)
- openai-like: Generic OpenAI-compatible (uses OPENAI_API_KEY + custom base_url)
"""

import logging
import os
from typing import TYPE_CHECKING, Any, cast

from agno.agent import Agent
from agno.db.postgres import PostgresDb
from agno.db.sqlite import SqliteDb
from agno.models.base import MessageData, Model
from agno.models.message import Message
from agno.models.openai import OpenAILike
from agno.models.openrouter import OpenRouter
from agno.models.response import ModelResponse

if TYPE_CHECKING:
    from src.config import Settings

logger = logging.getLogger(__name__)


def _is_complete_function_call(tool_call: dict[str, Any]) -> bool:
    """Return whether a provider tool call is safe to execute and replay.

    Some OpenRouter model/provider combinations have emitted an empty tool
    call alongside a valid one. Agno 2.9 adds a UUID to that empty entry and
    persists it, but the provider rejects the malformed history next turn.
    """
    function = tool_call.get("function")
    name = function.get("name") if isinstance(function, dict) else None
    return (
        tool_call.get("type") == "function"
        and isinstance(function, dict)
        and isinstance(name, str)
        and bool(name.strip())
    )


class ToolCallSafetyMixin(Model):
    """Shared Agno message-boundary safeguard, not a standalone provider.

    BL-16: apply to direct OpenRouter and OpenAI-compatible Gateway responses.
    Validate structural completeness only; argument parsing and authorization
    remain Agno/Core responsibilities. Never filter individual streaming deltas.
    """

    def _complete_tool_calls(
        self, tool_calls: list[dict[str, Any]] | None, *, streaming: bool = False
    ) -> list[dict[str, Any]] | None:
        """Filter final calls without logging names, arguments or response data."""
        calls = tool_calls or []
        complete_calls = [call for call in calls if _is_complete_function_call(call)]
        dropped_calls = len(calls) - len(complete_calls)
        if dropped_calls:
            logger.warning(
                "Dropped %d malformed %stool call(s) from model %s",
                dropped_calls,
                "streaming " if streaming else "",
                self.id,
            )
        # Agno 2.9.0 treats [] as another tool iteration in streaming. None
        # terminates the loop without a request lacking any executable tool.
        return complete_calls or None

    def _populate_assistant_message(
        self,
        assistant_message: Message,
        provider_response: ModelResponse,
    ) -> Message:
        """Sanitize consolidated tool calls before Agno executes or stores them.

        This is deliberately applied after streaming deltas are consolidated:
        individual deltas may be incomplete, while the final calls may not.
        """
        # ModelResponse annotates a list, but Agno message loops also accept
        # None as "no calls". Keep that compatibility localized to this adapter.
        cast(Any, provider_response).tool_calls = self._complete_tool_calls(
            provider_response.tool_calls
        )
        return super()._populate_assistant_message(
            assistant_message,
            provider_response,
        )

    def _populate_assistant_message_from_stream_data(
        self,
        assistant_message: Message,
        stream_data: MessageData,
    ) -> None:
        """Sanitize consolidated streaming tool calls before execution/storage."""
        super()._populate_assistant_message_from_stream_data(
            assistant_message,
            stream_data,
        )
        assistant_message.tool_calls = self._complete_tool_calls(
            assistant_message.tool_calls, streaming=True
        )


class SafeOpenRouter(ToolCallSafetyMixin, OpenRouter):
    """OpenRouter adapter that drops malformed tool calls before persistence."""


class SafeOpenAILike(ToolCallSafetyMixin, OpenAILike):
    """OpenAI-compatible adapter with the same safeguard, including LiteLLM."""


def create_db(db_url: str | None = None) -> PostgresDb | SqliteDb:
    """Create the Agno runtime database.

    Uses PostgreSQL if AGNO_DATABASE_URL is set, otherwise defaults to SQLite.
    Agno runtime tables always live in the dedicated ``agno_runtime`` schema.
    """
    if db_url:
        return PostgresDb(db_url=db_url, db_schema="agno_runtime")
    os.makedirs("tmp", exist_ok=True)
    return SqliteDb(
        session_table="ancoramind_sessions",
        db_file="tmp/ancoramind.db",
    )


def resolve_model_parts(
    provider: str = "openai",
    model_id: str = "gpt-6-luna",
    base_url: str | None = None,
    api_key: str | None = None,
) -> tuple[type[Model], dict[str, Any]]:
    """Resolve the concrete Agno model class and its constructor kwargs.

    Shared by the legacy singleton factory (transitional until the T4/T5
    rollout retires the AgentOS webhook) and by LLMAccess, which composes the
    governed mixin on top of the returned class (specs/013 T7).

    Returns:
        Tuple of (model class, constructor kwargs without ``retries``).
    """
    normalized = provider.lower().strip()

    if normalized == "openai":
        from agno.models.openai import OpenAIChat

        kwargs: dict[str, Any] = {"id": model_id}
        if api_key:
            kwargs["api_key"] = api_key
        if base_url:
            kwargs["base_url"] = base_url
        return OpenAIChat, kwargs

    if normalized == "openrouter":
        kwargs = {"id": model_id}
        if api_key:
            kwargs["api_key"] = api_key
        if base_url:
            kwargs["base_url"] = base_url
        return SafeOpenRouter, kwargs

    if normalized == "openai-like":
        if not base_url:
            raise ValueError(
                "LLM_BASE_URL is required when LLM_PROVIDER=openai-like. "
                "Example: https://api.groq.com/openai/v1"
            )
        kwargs = {"id": model_id, "base_url": base_url}
        if api_key:
            kwargs["api_key"] = api_key
        return SafeOpenAILike, kwargs

    raise ValueError(
        f"Unsupported LLM_PROVIDER: {provider!r}. Use one of: openai, openrouter, openai-like"
    )


def create_model(
    provider: str = "openai",
    model_id: str = "gpt-6-luna",
    base_url: str | None = None,
    api_key: str | None = None,
    retries: int = 0,
) -> Model:
    """Create the LLM model instance for the configured provider.

    Providers:
        openai:      OpenAIChat  — uses OPENAI_API_KEY env var
        openrouter:  OpenRouter  — uses OPENROUTER_API_KEY env var
        openai-like: OpenAILike  — uses OPENAI_API_KEY + custom base_url
                                   (Groq, Together, DeepSeek, Ollama, etc.)

    Args:
        provider: One of "openai", "openrouter", "openai-like".
        model_id: Model ID (e.g. "gpt-6-luna", "anthropic/claude-3.5-sonnet").
        base_url: Custom base URL (required for openai-like).
        api_key: Optional API key override (otherwise from env vars).
        retries: Model-level retries; the approved policy is explicitly 0.

    Returns:
        Configured model instance.
    """
    model_cls, kwargs = resolve_model_parts(provider, model_id, base_url, api_key)
    return model_cls(retries=retries, **kwargs)


def create_model_from_settings(settings: "Settings") -> Model:
    """Create the LLM model from application settings.

    Single source of truth for provider/model/base_url/api_key resolution,
    shared by the main agent (src.main) and the document extraction tool
    (agent/tools/documents.py — BL-10).

    Args:
        settings: Application settings (LLM_PROVIDER/LLM_MODEL/LLM_BASE_URL,
            OPENAI_API_KEY/OPENROUTER_API_KEY).

    Returns:
        Configured model instance.
    """
    if settings.litellm_proxy_enabled:
        return create_model(
            provider="openai-like",
            model_id=settings.litellm_proxy_default_route,
            base_url=_litellm_v1_base_url(settings.litellm_proxy_base_url),
            api_key=settings.litellm_proxy_virtual_key,
        )

    api_key = None
    if settings.llm_provider == "openrouter" and settings.openrouter_api_key:
        api_key = settings.openrouter_api_key
    elif settings.llm_provider == "openai" and settings.openai_api_key:
        api_key = settings.openai_api_key

    return create_model(
        provider=settings.llm_provider,
        model_id=settings.llm_model,
        base_url=settings.llm_base_url,
        api_key=api_key,
    )


def _litellm_v1_base_url(base_url: str) -> str:
    """Normalize a private LiteLLM Proxy URL to its OpenAI-compatible ``/v1`` API."""
    normalized = base_url.rstrip("/")
    return normalized if normalized.endswith("/v1") else f"{normalized}/v1"


def create_ancora_agent(
    model: Model | str,
    tools: list[Any],
    instructions: list[str],
    db: Any = None,
    tool_call_limit: int = 12,
    retries: int = 0,
) -> Agent:
    """Create the AncoraMind agent.

    Args:
        model: LLM model instance (OpenAIChat, OpenRouter, or OpenAILike).
        tools: List of plain Python functions — Agno auto-converts to tools.
        instructions: List of instruction strings (one per markdown prompt file).
        db: Agno database for session persistence.
        tool_call_limit: Hard safety ceiling for tool calls in one agent run
            (the approved specs/013 target is 12).
        retries: Agent-level retries; the approved policy is explicitly 0.

    Returns:
        Configured Agno Agent instance.
    """
    return Agent(
        name="AncoraMind",
        model=model,
        db=db,
        tools=tools,
        tool_call_limit=tool_call_limit,
        retries=retries,
        telemetry=False,
        instructions=instructions,
        add_history_to_context=True,
        num_history_runs=10,
        add_datetime_to_context=True,
        markdown=True,
        description=("AncoraMind — tu asistente personal inteligente con memoria operativa."),
    )
