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


def bounded_text(value: str, limit: int) -> tuple[str, bool]:
    """Return a display-only preview without modifying the canonical value."""
    return value[:limit], len(value) > limit


def render_retrieved_records(
    source: str, records: list[dict[str, object]], total: int
) -> str:
    """Put provenance and all untrusted fields in one parseable JSON object."""
    payload = {
        "trust": "untrusted_data",
        "source": source,
        "total_matches": total,
        "records_omitted": max(0, total - len(records)),
        "records": records,
    }
    return (
        "Datos recuperados:\n"
        + json.dumps(payload, ensure_ascii=True, separators=(",", ":"))
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
    )
