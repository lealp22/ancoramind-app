"""Unit tests for deterministic Phase 1 web-search policy."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from src.domain.web_search.models import WebSearchOutcome, WebSearchRequest, WebSearchResult
from src.domain.web_search.service import WebSearchPolicyError, WebSearchService


class _FakePort:
    def __init__(self) -> None:
        self.requests: list[WebSearchRequest] = []

    async def search(self, request: WebSearchRequest) -> WebSearchOutcome:
        self.requests.append(request)
        return WebSearchOutcome(
            provider="fake",
            results=(
                WebSearchResult(title="A", url="https://example.test/a", content="one"),
                WebSearchResult(title="B", url="https://example.test/b", content="two"),
            ),
            retrieved_at=datetime.now(tz=UTC),
        )


async def test_service_normalizes_bounds_and_caches_query() -> None:
    port = _FakePort()
    service = WebSearchService(port, max_results=1, cache_ttl_seconds=300)

    first = await service.search("  tema\n público  ")
    second = await service.search("tema público")

    assert len(port.requests) == 1
    assert port.requests[0] == WebSearchRequest(query="tema público", max_results=1)
    assert len(first.results) == 1
    assert first.cache_hit is False
    assert second.cache_hit is True
    assert second.results == first.results


@pytest.mark.parametrize(
    ("query", "reason"),
    [
        ("", "empty_query"),
        ("x" * 301, "query_too_long"),
        ("contacta persona@example.com", "sensitive_query"),
        ("llama al +34 612 345 678", "sensitive_query"),
        ("DNI 12345678", "sensitive_query"),
    ],
)
async def test_service_rejects_out_of_policy_queries(query: str, reason: str) -> None:
    port = _FakePort()
    service = WebSearchService(port, max_results=5, cache_ttl_seconds=300)

    with pytest.raises(WebSearchPolicyError, match=reason):
        await service.search(query)

    assert port.requests == []
