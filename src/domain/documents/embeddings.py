"""Governed embedding boundary for document semantic retrieval (specs/026)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class DocumentEmbeddingOutcome:
    """Controlled result of embedding one bounded, untrusted document payload.

    Error metadata must be a bounded operational class only. Implementations
    must not place input text, provider payloads, or secrets in this outcome.
    """

    embedding: tuple[float, ...] | None
    provider: str
    model: str
    status: str
    error_class: str | None = None


class DocumentEmbeddingPort(Protocol):
    """Infrastructure-owned, governed embedding boundary.

    The documents domain requests vectors only through this port. Implementors
    resolve the configured logical route and must fail closed rather than create
    a provider client from the domain layer.
    """

    async def embed(self, text: str) -> DocumentEmbeddingOutcome: ...
