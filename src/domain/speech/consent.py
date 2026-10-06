"""Voice phrase classification only; never a claim or proof of authorization."""

from __future__ import annotations

import re
from enum import StrEnum

_VOICE_CONSENT = re.compile(r"(?:sí|si|no)", re.IGNORECASE)


class VoiceConsentIntent(StrEnum):
    CONFIRM = "confirm"
    DISCARD = "discard"


def parse_voice_consent_intent(text: str | None) -> VoiceConsentIntent | None:
    """Recognize an isolated Sí/No, not quotes, IDs, callbacks or commands.

    Origin, presentation, expiry and an atomic Core claim MUST be checked by the
    caller. Parsing a document or a fabricated transcript cannot confer consent.
    """
    if not isinstance(text, str) or len(text) > 64:
        return None
    normalized = text.strip(" ")
    if normalized.startswith("¡"):
        normalized = normalized[1:]
    if normalized.endswith(("!", ".")):
        normalized = normalized[:-1]
    if _VOICE_CONSENT.fullmatch(normalized) is None:
        return None
    return VoiceConsentIntent.DISCARD if normalized.lower() == "no" else VoiceConsentIntent.CONFIRM
