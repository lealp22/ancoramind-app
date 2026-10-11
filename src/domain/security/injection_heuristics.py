"""Deterministic, offline heuristics for prompt-injection-shaped text (BL-39 piloto).

Pure, stateless, no I/O, no network, no dependency on untrusted_results or
any Agno/LLM machinery. **This is an observability signal, not a gate**:
nothing in the governed authorization path (`propose_*`/`execute_*`, P0)
reads this module, and it is not wired into any production tool in this
increment — it exists to measure recall/false-positive rate against
`evals/security/cases.json` before any decision to adopt/wire it
(docs/llm-security-hardening.md §"Capa 4"). A false negative here can never
open a bypass, because authorization never depends on it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_IMPERATIVE_OVERRIDE_WHITESPACE_RE = re.compile(r"[\s_]+")
_IMPERATIVE_OVERRIDE_TARGET_WORDS = ("execut", "confirm", "obedec", "instruc")
_FAKE_ROLE_PREFIX_RE = re.compile(r"\bSYSTEM:", re.IGNORECASE)
_BIDI_CONTROL_CHARS = frozenset(
    "‮‭‎‏⁦⁧⁨⁩"
)
_BASE64_BLOB_RE = re.compile(r"[A-Za-z0-9+/]{16,}={0,2}")
_DECODE_VERB_RE = re.compile(r"decod\w*|obedec\w*|ejecut\w*", re.IGNORECASE)
_LINK_WITH_VERB_RE = re.compile(r"(visita|accede a|entra en)\s+https?://", re.IGNORECASE)
_LINK_FOLLOWED_BY_VERB_RE = re.compile(
    r"https?://\S+\s+y\s+(env[ií]a|manda|comparte)", re.IGNORECASE
)


@dataclass(frozen=True)
class InjectionSignal:
    """Result of scanning one piece of untrusted text. Logging-only."""

    matched: bool
    reasons: tuple[str, ...]


def scan_for_injection_patterns(text: str) -> InjectionSignal:
    """Scan untrusted text for deterministic prompt-injection shapes.

    Each reason is independent and documented at its regex definition
    above; several may fire on the same text. Calibrated against
    `evals/security/cases.json` to avoid matching the two benign-control
    cases there — not validated against any larger real-world corpus.
    """
    reasons: list[str] = []
    if _has_imperative_override(text):
        reasons.append("imperative_override")
    if _FAKE_ROLE_PREFIX_RE.search(text):
        reasons.append("fake_role_prefix")
    if any(char in _BIDI_CONTROL_CHARS for char in text):
        reasons.append("unicode_bidi_control")
    if _has_base64_blob_with_decode_instruction(text):
        reasons.append("base64_blob_with_decode_instruction")
    if _LINK_WITH_VERB_RE.search(text) or _LINK_FOLLOWED_BY_VERB_RE.search(text):
        reasons.append("exfiltration_link_prompt")
    return InjectionSignal(matched=bool(reasons), reasons=tuple(reasons))


def _has_imperative_override(text: str) -> bool:
    # Plain string scan (not a nested-quantifier regex, which risks
    # superlinear backtracking on adversarial input): normalize separators
    # so "ignore_execute" and "ignore execute" are both just substrings,
    # then require a target verb within a short window after "ignor".
    normalized = _IMPERATIVE_OVERRIDE_WHITESPACE_RE.sub(" ", text.lower())
    start = normalized.find("ignor")
    if start == -1:
        return False
    window = normalized[start : start + 60]
    return any(word in window for word in _IMPERATIVE_OVERRIDE_TARGET_WORDS)


def _has_base64_blob_with_decode_instruction(text: str) -> bool:
    for match in _BASE64_BLOB_RE.finditer(text):
        # A URL path segment ("invalid/warranty") is also 16+ chars of
        # [A-Za-z0-9+/] — real base64 almost always mixes in a digit, a
        # lowercase-only run of words joined by "/" never does.
        if not any(char.isdigit() for char in match.group()):
            continue
        window = text[match.end() : match.end() + 60]
        if _DECODE_VERB_RE.search(window):
            return True
    return False


__all__ = ["InjectionSignal", "scan_for_injection_patterns"]
