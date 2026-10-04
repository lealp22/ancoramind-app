"""Deterministic policy and transient cache for public web searches."""

from __future__ import annotations

import re
import time
from dataclasses import replace

from src.domain.web_search.models import WebSearchOutcome, WebSearchRequest
from src.domain.web_search.port import WebSearchPort

MAX_QUERY_CHARS = 300


class WebSearchPolicyError(ValueError):
    """The requested lookup is outside the approved Phase 1 policy."""


class WebSearchService:
    """Run bounded public-information searches through an injected provider.

    The cache is process-local and intentionally contains no persistence or
    logging. Queries that look likely to contain personal/sensitive data are
    rejected rather than sent to a third party because Phase 1 has no separate
    consent flow for external search.
    """

    _EMAIL = re.compile(r"\b[^\s@]+@[^\s@]+\.[^\s@]+\b")
    _PHONE = re.compile(r"(?<!\d)(?:\+?\d[\s().-]*){8,}\d(?!\d)")
    _LONG_IDENTIFIER = re.compile(r"\b\d{8,}\b")

    def __init__(
        self,
        provider: WebSearchPort,
        *,
        max_results: int,
        cache_ttl_seconds: int,
    ) -> None:
        self._provider = provider
        self._max_results = max_results
        self._cache_ttl_seconds = cache_ttl_seconds
        self._cache: dict[str, tuple[float, WebSearchOutcome]] = {}

    async def search(self, query: str) -> WebSearchOutcome:
        """Validate, minimize and search one public query."""
        normalized = " ".join(query.split())
        self._validate_query(normalized)
        cached = self._cache.get(normalized.casefold())
        now = time.monotonic()
        if cached is not None and now - cached[0] < self._cache_ttl_seconds:
            return replace(cached[1], cache_hit=True)

        outcome = await self._provider.search(
            WebSearchRequest(query=normalized, max_results=self._max_results)
        )
        bounded = replace(outcome, results=outcome.results[: self._max_results])
        self._cache[normalized.casefold()] = (now, bounded)
        return bounded

    @classmethod
    def _validate_query(cls, query: str) -> None:
        if not query:
            raise WebSearchPolicyError("empty_query")
        if len(query) > MAX_QUERY_CHARS:
            raise WebSearchPolicyError("query_too_long")
        if any(pattern.search(query) for pattern in (cls._EMAIL, cls._PHONE, cls._LONG_IDENTIFIER)):
            raise WebSearchPolicyError("sensitive_query")
