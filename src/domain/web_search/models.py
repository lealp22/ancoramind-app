"""Provider-neutral models for the bounded web-search capability."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class WebSearchRequest:
    """A minimized public-information lookup approved by the domain."""

    query: str
    max_results: int


@dataclass(frozen=True)
class WebSearchResult:
    """One public source returned by a search provider.

    All fields are untrusted third-party data and must be bounded before they
    are exposed to the Agent.
    """

    title: str
    url: str
    content: str
    published_date: str | None = None


@dataclass(frozen=True)
class WebSearchOutcome:
    """Normalized result of a single provider lookup."""

    provider: str
    results: tuple[WebSearchResult, ...]
    retrieved_at: datetime
    provider_request_id: str | None = None
    credits: int | None = None
    response_time_seconds: float | None = None
    cache_hit: bool = False
