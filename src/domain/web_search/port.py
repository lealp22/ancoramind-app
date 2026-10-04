"""Provider boundary for public web search."""

from __future__ import annotations

from typing import Protocol

from src.domain.web_search.models import WebSearchOutcome, WebSearchRequest


class WebSearchPort(Protocol):
    """Physical provider boundary; implementations must not expose raw HTTP payloads."""

    async def search(self, request: WebSearchRequest) -> WebSearchOutcome: ...
