"""HTTP-contract tests for the bounded Tavily adapter."""

from __future__ import annotations

import json

import httpx
import pytest

from src.agent.tavily_web_search import TAVILY_SEARCH_URL, TavilyWebSearchError, TavilyWebSearchPort
from src.domain.web_search.models import WebSearchRequest


async def test_tavily_adapter_uses_fixed_phase_one_request_surface() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["auth"] = request.headers.get("Authorization")
        captured["payload"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "request_id": "request-1",
                "response_time": 0.25,
                "usage": {"credits": 1},
                "results": [
                    {
                        "title": "Fuente",
                        "url": "https://example.test/source",
                        "content": "Texto recuperado",
                        "published_date": "2026-10-04",
                    }
                ],
            },
        )

    adapter = TavilyWebSearchPort(
        "tvly-secret",
        timeout_seconds=2,
        transport=httpx.MockTransport(handler),
    )
    outcome = await adapter.search(WebSearchRequest(query="tema público", max_results=3))

    assert captured["url"] == TAVILY_SEARCH_URL
    assert captured["auth"] == "Bearer tvly-secret"
    assert captured["payload"] == {
        "query": "tema público",
        "search_depth": "basic",
        "max_results": 3,
        "topic": "general",
        "include_answer": False,
        "include_raw_content": False,
        "include_images": False,
        "include_published_date": True,
        "include_usage": True,
        "auto_parameters": False,
        "safe_search": True,
    }
    assert outcome.provider == "tavily"
    assert outcome.provider_request_id == "request-1"
    assert outcome.credits == 1
    assert outcome.results[0].published_date == "2026-10-04"


@pytest.mark.parametrize("response", [httpx.Response(429), httpx.Response(200, text="not-json")])
async def test_tavily_adapter_hides_provider_failure_details(response: httpx.Response) -> None:
    adapter = TavilyWebSearchPort(
        "tvly-secret",
        timeout_seconds=2,
        transport=httpx.MockTransport(lambda _: response),
    )

    with pytest.raises(TavilyWebSearchError) as exc_info:
        await adapter.search(WebSearchRequest(query="tema", max_results=3))

    assert str(exc_info.value) in {"http_429", "invalid_response"}
    assert "secret" not in str(exc_info.value)
