"""Deterministic detection and masking of sensitive identifiers (ADR-007).

Pure Python, no Agno/OpenTelemetry dependency. Pattern matches are validated
(checksum or format) where the format allows it, to keep false positives low on
everyday Spanish text. Unrecognised long digit runs are masked by default as a
safety net. Patterns are incomplete by design: they do not detect names,
addresses or health data, and masking is not anonymisation.
"""

from __future__ import annotations

import re
from collections.abc import Callable

_DNI_LETTERS = "TRWAGMYFPDXBNJZSQVHLCKE"

_CARD = re.compile(r"(?<!\d)\d(?:[ -]?\d){12,18}(?!\d)")
_IBAN = re.compile(r"\b[A-Z]{2}\d{2}(?:\s?[A-Z0-9]{4}){3,7}(?:\s?[A-Z0-9]{1,3})?\b", re.IGNORECASE)
_DNI = re.compile(r"\b\d{8}[- ]?[A-Z]\b", re.IGNORECASE)
_NIE = re.compile(r"\b[XYZ][- ]?\d{7}[- ]?[A-Z]\b", re.IGNORECASE)
_PLATE_MODERN = re.compile(r"\b\d{4}[- ]?[B-DF-HJ-NP-TV-Z]{3}\b", re.IGNORECASE)
_PLATE_LEGACY = re.compile(r"\b[A-Z]{1,2}[- ]?\d{4}[- ]?[A-Z]{1,2}\b")
_VIN = re.compile(r"\b[A-HJ-NPR-Z0-9]{17}\b")
_EMAIL = re.compile(r"\b[^\s@]+@[^\s@]+\.[^\s@]+\b")
_TOKEN_PREFIXED = re.compile(
    r"\b(?:sk-|tvly-|ghp_|gho_|github_pat_|xox[abprs]-|AKIA)[A-Za-z0-9_\-]{8,}|\beyJ[A-Za-z0-9_\-]{10,}"
)
_TOKEN_ENTROPY = re.compile(r"\b[A-Za-z0-9_\-]{32,}\b")
_PHONE = re.compile(r"(?<!\d)(?:\+?\d[\s().-]*){8,}\d(?!\d)")
_LONG_NUMBER = re.compile(r"\b\d{8,}\b")


def _digits(value: str) -> str:
    return "".join(ch for ch in value if ch.isdigit())


def _luhn_ok(value: str) -> bool:
    digits = _digits(value)
    if not 13 <= len(digits) <= 19:
        return False
    total = 0
    for index, ch in enumerate(reversed(digits)):
        number = int(ch)
        if index % 2 == 1:
            number *= 2
            if number > 9:
                number -= 9
        total += number
    return total % 10 == 0


def _iban_ok(value: str) -> bool:
    compact = re.sub(r"\s", "", value).upper()
    if not 15 <= len(compact) <= 34:
        return False
    rearranged = compact[4:] + compact[:4]
    numeric = "".join(str(int(ch, 36)) for ch in rearranged)
    return int(numeric) % 97 == 1


def _dni_ok(value: str) -> bool:
    compact = re.sub(r"[- ]", "", value).upper()
    return _DNI_LETTERS[int(compact[:8]) % 23] == compact[8]


def _nie_ok(value: str) -> bool:
    compact = re.sub(r"[- ]", "", value).upper()
    number = int("XYZ".index(compact[0]) * 10**7 + int(compact[1:8]))
    return _DNI_LETTERS[number % 23] == compact[8]


def _vin_ok(value: str) -> bool:
    return any(ch.isdigit() for ch in value) and any(ch.isalpha() for ch in value)


def _entropy_ok(value: str) -> bool:
    return any(ch.isdigit() for ch in value) and any(ch.isalpha() for ch in value)


def _always(_value: str) -> bool:
    return True


def _legacy_plate_ok(value: str) -> bool:
    # Case-sensitive on purpose: lowercase `de 2024 ab` style text is not a plate.
    return value == value.upper()


# Order matters: validated, more specific detectors run before the generic ones.
_DETECTORS: tuple[tuple[str, str, re.Pattern[str], Callable[[str], bool]], ...] = (
    ("card", "[TARJETA]", _CARD, _luhn_ok),
    ("iban", "[IBAN]", _IBAN, _iban_ok),
    ("nie", "[NIE]", _NIE, _nie_ok),
    ("dni", "[DNI]", _DNI, _dni_ok),
    ("plate", "[MATRICULA]", _PLATE_MODERN, _always),
    ("plate", "[MATRICULA]", _PLATE_LEGACY, _legacy_plate_ok),
    ("vin", "[BASTIDOR]", _VIN, _vin_ok),
    ("email", "[EMAIL]", _EMAIL, _always),
    ("token", "[TOKEN]", _TOKEN_PREFIXED, _always),
    ("token", "[TOKEN]", _TOKEN_ENTROPY, _entropy_ok),
    ("phone", "[TELEFONO]", _PHONE, _always),
    ("number", "[NUMERO]", _LONG_NUMBER, _always),
)


def scan_sensitive(text: str) -> tuple[str, frozenset[str]]:
    """Return ``(masked_text, detected_kinds)`` for one piece of free text."""
    kinds: set[str] = set()
    masked = text
    for kind, marker, pattern, is_valid in _DETECTORS:

        def _replace(
            match: re.Match[str],
            kind: str = kind,
            marker: str = marker,
            is_valid: Callable[[str], bool] = is_valid,
        ) -> str:
            if not is_valid(match.group(0)):
                return match.group(0)
            kinds.add(kind)
            return marker

        masked = pattern.sub(_replace, masked)
    return masked, frozenset(kinds)


def detect_sensitive(text: str) -> frozenset[str]:
    """Kinds of sensitive identifiers found in ``text`` (empty when none)."""
    return scan_sensitive(text)[1]


def mask_sensitive(text: str) -> str:
    """Replace recognised sensitive identifiers with typed markers."""
    return scan_sensitive(text)[0]
