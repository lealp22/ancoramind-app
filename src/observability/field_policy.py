"""Schema layer of the Phoenix masking (ADR-007 layer 1, specs/046 T2).

Decides how one argument of a ``propose_*`` tool is treated from its FIELD NAME and,
where noted, the SHAPE of its value. It does not look at free text for patterns: that
is ``masking.py``'s job and runs on every value this policy lets through as text.

Classes, from most to least protected:

* ``IDENTIFIER``: personal identifiers. Replaced by a typed marker whatever the
  value looks like, because a plate or VIN written oddly escapes the patterns.
* ``FREE_TEXT``: user prose (titles, notes, places). It is the content worth seeing
  for diagnosis, so it is kept and masked by pattern, not hidden.
* ``INTERNAL_ID``: a UUID that points at a row of our own database. Kept as is: it is
  how a trace is correlated with PostgreSQL and it is not personal data by itself.
  Kept ONLY when the value really is a UUID; a field named ``*_id`` holding anything
  else becomes ``INVALID_MARKER``, so the name alone never grants an exemption and
  prose cannot ride in an id field.
* ``STRUCTURED``: dates, counts, amounts, enums, booleans. Kept only when the value
  has the strict shape of its field; otherwise ``INVALID_MARKER``. Once validated no
  free text can hide in them, so they bypass the numeric safety net that exists for
  unrecognised long digit runs in prose.

Anything not listed is ``FREE_TEXT``: an unclassified field is masked by pattern, never
trusted. A drift test fails when a ``propose_*`` parameter is added without being
classified here.

Known limit: ``FREE_TEXT`` is masked by pattern only, and patterns see formats (DNI,
IBAN, phone...), not names, addresses or health data. That is the accepted trade-off
of ADR-007 for the fields whose content is the point of the trace.
"""

from __future__ import annotations

import re
from enum import Enum
from uuid import UUID

INVALID_MARKER = "[INVALIDO]"
"""Stands in for a value that does not have the shape its field allows."""


class FieldClass(Enum):
    IDENTIFIER = "identifier"
    FREE_TEXT = "free_text"
    INTERNAL_ID = "internal_id"
    STRUCTURED = "structured"


# Personal identifiers -> typed marker. Matches masking.py's markers.
IDENTIFIER_MARKERS: dict[str, str] = {
    "registration": "[MATRICULA]",
    "vin": "[BASTIDOR]",
    "user_id": "[USUARIO]",
    "telegram_user_id": "[USUARIO]",
    "email": "[EMAIL]",
    "phone": "[TELEFONO]",
    "iban": "[IBAN]",
    "dni": "[DNI]",
    "nie": "[NIE]",
}

# Prose written by the user (or lifted from a document by the user's request).
FREE_TEXT_FIELDS = frozenset(
    {
        "title",
        "description",
        "content",
        "notes",
        "name",
        "location",
        "workshop",
        "work_performed",
        "nickname",
        "make",
        "model",
    }
)

# Fields that hold a pointer to one of our own rows (kept only if the value is a UUID).
INTERNAL_ID_FIELDS = frozenset(
    {
        "list_id",
        "item_id",
        "target_list_id",
        "vehicle_id",
        "reminder_id",
        "document_id",
        "source_document_id",
        "candidate_id",
        "proposal_id",
    }
)

# Validated, non-prose values. Dates stay strings; the pattern for them is strict.
STRUCTURED_FIELDS = frozenset(
    {
        "year",
        "mileage_km",
        "cost_amount",
        "cost_currency",
        "priority",
        "minutes",
        "with_reminder",
        "reminder_lead_minutes",
        "recurrence_frequency",
        "recurrence_interval",
        "recurrence_until",
        "start_at",
        "end_at",
        "trigger_at",
        "due_date",
        "date_str",
    }
)

ALL_CLASSIFIED = (
    frozenset(IDENTIFIER_MARKERS) | FREE_TEXT_FIELDS | INTERNAL_ID_FIELDS | STRUCTURED_FIELDS
)

# ISO-8601 date or datetime with optional offset; nothing else qualifies as a date.
_ISO_TEMPORAL = re.compile(
    r"\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}(?::\d{2}(?:\.\d{1,6})?)?(?:Z|[+-]\d{2}:\d{2})?)?"
)
_AMOUNT = re.compile(r"\d{1,9}(?:[.,]\d{1,2})?")
_CURRENCY = re.compile(r"[A-Z]{3}")
_ENUM = re.compile(r"[a-z_]{1,20}")
_MAX_INT = 10**9


def classify(name: str) -> FieldClass:
    """Class of a field by (case-insensitive) name; unlisted names are ``FREE_TEXT``."""
    lowered = name.lower()
    if lowered in IDENTIFIER_MARKERS:
        return FieldClass.IDENTIFIER
    if lowered in INTERNAL_ID_FIELDS:
        return FieldClass.INTERNAL_ID
    if lowered in STRUCTURED_FIELDS:
        return FieldClass.STRUCTURED
    return FieldClass.FREE_TEXT


def is_uuid(value: object) -> bool:
    """True only for the canonical 36-character form (no braces, urn or bare hex)."""
    if not isinstance(value, str) or len(value) != 36:
        return False
    try:
        return str(UUID(value)) == value.lower()
    except ValueError:
        return False


def is_valid_structured(name: str, value: object) -> bool:
    """Whether ``value`` has the strict shape its structured field allows.

    A value that fails is replaced by ``INVALID_MARKER`` by the caller, never exported:
    a free-text string in ``year`` or ``due_date`` is unexpected, and pattern masking
    could not see a name in it.
    """
    lowered = name.lower()
    if value is None or isinstance(value, bool):
        return True
    if isinstance(value, int):
        return 0 <= value <= _MAX_INT
    if not isinstance(value, str):
        return False
    if lowered in {"start_at", "end_at", "trigger_at", "due_date", "date_str", "recurrence_until"}:
        return _ISO_TEMPORAL.fullmatch(value) is not None
    if lowered == "cost_amount":
        return _AMOUNT.fullmatch(value) is not None
    if lowered == "cost_currency":
        return _CURRENCY.fullmatch(value) is not None
    if lowered in {"priority", "recurrence_frequency"}:
        return _ENUM.fullmatch(value) is not None
    return False
