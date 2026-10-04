"""Tavily HTTP adapter for the governed web-search domain capability."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import httpx

from src.domain.web_search.models import WebSearchOutcome, WebSearchRequest, WebSearchResult

TAVILY_SEARCH_URL = "https://api.tavily.com/search"


class TavilyWebSearchError(RuntimeError):
    """A controlled Tavily transport or response failure."""


class TavilyWebSearchPort:
    """Minimal Tavily adapter with a fixed Phase 1 request surface.

    Tavily's generated answer and raw page content are intentionally disabled:
    the governed Agent synthesizes bounded source snippets itself.
    """

    def __init__(
        self,
        api_key: str,
        *,
        timeout_seconds: float,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._api_key = api_key
        self._timeout_seconds = timeout_seconds
        self._transport = transport

    async def search(self, request: WebSearchRequest) -> WebSearchOutcome:
        payload = {
            "query": request.query,
            "search_depth": "basic",
            "max_results": request.max_results,
            "topic": "general",
            "include_answer": False,
            "include_raw_content": False,
            "include_images": False,
            "include_published_date": True,
            "include_usage": True,
            "auto_parameters": False,
            "safe_search": True,
        }
        try:
            async with httpx.AsyncClient(
                timeout=self._timeout_seconds,
                transport=self._transport,
            ) as client:
                response = await client.post(
                    TAVILY_SEARCH_URL,
                    headers={"Authorization": f"Bearer {self._api_key}"},
                    json=payload,
                )
        except httpx.HTTPError as exc:
            raise TavilyWebSearchError("transport_error") from exc

        if response.status_code != 200:
            raise TavilyWebSearchError(f"http_{response.status_code}")
        try:
            body: dict[str, Any] = response.json()
        except ValueError as exc:
            raise TavilyWebSearchError("invalid_response") from exc

        raw_results = body.get("results")
        if not isinstance(raw_results, list):
            raise TavilyWebSearchError("invalid_results")
        results: list[WebSearchResult] = []
        for item in raw_results:
            if not isinstance(item, dict):
                continue
            title = item.get("title")
            url = item.get("url")
            content = item.get("content")
            if not isinstance(title, str) or not title.strip():
                continue
            if not isinstance(url, str) or not url.strip():
                continue
            if not isinstance(content, str) or not content.strip():
                continue
            published_date = item.get("published_date")
            results.append(
                WebSearchResult(
                    title=title.strip(),
                    url=url.strip(),
                    content=content.strip(),
                    published_date=published_date if isinstance(published_date, str) else None,
                )
            )

        usage = body.get("usage")
        credits = usage.get("credits") if isinstance(usage, dict) else None
        response_time = body.get("response_time")
        request_id = body.get("request_id")
        return WebSearchOutcome(
            provider="tavily",
            results=tuple(results),
            retrieved_at=datetime.now(tz=UTC),
            provider_request_id=request_id if isinstance(request_id, str) else None,
            credits=credits if isinstance(credits, int) else None,
            response_time_seconds=float(response_time)
            if isinstance(response_time, (int, float))
            else None,
        )
