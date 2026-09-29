"""Parse an isolated confirmation phrase; never treat it as authorization.

Authorization requires a separate, trusted, durable interaction and an atomic
Core claim (specs/022-llm-input-trust/consent-design.md). This parser only
recognizes the narrow text UX; callers must not execute actions from its output.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from uuid import UUID

_UUID = r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}"
_CONFIRMATION = re.compile(rf"(?:sí|si)(?:[ ]+(?P<proposal_id>{_UUID}))?", re.IGNORECASE)


@dataclass(frozen=True)
class ConsentIntent:
    """Untrusted text classification, NOT a proof that a user consented."""

    proposal_id: UUID | None


def parse_consent_intent(text: str | None) -> ConsentIntent | None:
    """Accept only an isolated 'Sí' or 'Sí <canonical UUID>' text message.

    Capitalization and one trailing period/exclamation mark are tolerated.
    This function knows nothing about authorship, delivery, expiry or payload:
    it must never be used as an authorization gate on its own.
    """
    if not isinstance(text, str) or len(text) > 64:
        return None
    normalized = text.strip(" ")
    if normalized.startswith("¡"):
        normalized = normalized[1:]
    if normalized.endswith(("!", ".")):
        normalized = normalized[:-1]
    match = _CONFIRMATION.fullmatch(normalized)
    if match is None:
        return None
    proposal_id = match.group("proposal_id")
    return ConsentIntent(proposal_id=UUID(proposal_id) if proposal_id is not None else None)
