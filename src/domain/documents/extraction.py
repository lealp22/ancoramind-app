"""DocumentExtractionPort — domain-owned inference boundary (specs/013 T9).

The documents domain no longer builds runtime agents directly. Extraction
inference is requested through this port; the physical model, agent loop and
provider details stay behind it in the infrastructure layer, resolved through
LLMAccess so the call shares the governed run's snapshot, budget, cost and
trace when one exists.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from pydantic import BaseModel


@dataclass(frozen=True)
class DocumentVisualPage:
    """One transient rendered page supplied to a vision-capable extraction port."""

    content: bytes
    mime_type: str


@dataclass(frozen=True)
class DocumentExtractionOutcome[TSchema: BaseModel]:
    """Controlled, observable outcome of one extraction inference call.

    ``error_class``/``error_detail`` carry bounded operational metadata only;
    implementations must never place document content or prompts there.
    """

    extraction: TSchema | None
    provider: str
    model: str
    status: str
    error_class: str | None = None
    error_detail: str | None = None


class DocumentExtractionPort(Protocol):
    """Inference boundary owned by the documents domain.

    Implementations must resolve the model through LLMAccess (fail closed
    rather than bypassing the governed frontier) and must surface inference
    failures as a controlled outcome instead of silently swallowing them.
    """

    async def extract[TSchema: BaseModel](
        self,
        prompt: str,
        schema: type[TSchema],
        visual_pages: tuple[DocumentVisualPage, ...] = (),
    ) -> DocumentExtractionOutcome[TSchema]: ...
