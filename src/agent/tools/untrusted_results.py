"""Bounded presentation of retrieved records to the Agent (BL-39).

This is a syntactic data boundary, not an authorization or prompt-injection
detector. Callers must never treat retrieved values as user consent.
"""

import json

MAX_RESULT_RECORDS = 10
MAX_NOTE_CHARS = 1200
MAX_FILENAME_CHARS = 255
MAX_SUMMARY_CHARS = 1200
#: Short free-text fields (vehicle make/model/nickname, reminder/event
#: title, TODO list name...). Same bound as MAX_FILENAME_CHARS, named for
#: readability at the call site.
MAX_TITLE_CHARS = 255


def _render_payload(source: str, records: list[dict[str, object]], total: int) -> str:
    """Serialize the stable untrusted-data envelope without exposing raw fields."""
    payload = {
        "trust": "untrusted_data",
        "source": source,
        "total_matches": total,
        "records_omitted": max(0, total - len(records)),
        "records": records,
    }
    return "Datos recuperados:\n" + json.dumps(
        payload, ensure_ascii=True, separators=(",", ":")
    ).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")


def bounded_text(value: str, limit: int) -> tuple[str, bool]:
    """Return a display-only preview without modifying the canonical value."""
    return value[:limit], len(value) > limit


def render_retrieved_records(
    source: str,
    records: list[dict[str, object]],
    total: int,
    *,
    max_chars: int | None = None,
) -> str:
    """Put provenance and all untrusted fields in one parseable JSON object."""
    if max_chars is None:
        return _render_payload(source, records, total)
    if max_chars <= 0:
        raise ValueError("max_chars must be positive")

    bounded_records: list[dict[str, object]] = []
    for record in records:
        candidate = [*bounded_records, record]
        if len(_render_payload(source, candidate, total)) > max_chars:
            break
        bounded_records = candidate
    rendered = _render_payload(source, bounded_records, total)
    if len(rendered) > max_chars:
        raise ValueError("max_chars is too small for the untrusted-data envelope")
    return rendered
