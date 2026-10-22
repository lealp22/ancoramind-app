"""Presentation-only dates: local time, explicit zone and lossless precision.

Never use this projection for parsing, authorization or proposal hashes.
Naive instants are localized only with an explicitly supplied user timezone.
"""

from __future__ import annotations

import re
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from src.domain.preferences.timezone import AmbiguousOrNonExistentTimeError, to_utc

_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")


def format_temporal(
    value: str | date,
    tz: ZoneInfo | None = None,
    *,
    allow_date: bool = True,
    naive_midnight_is_date: bool = False,
) -> str:
    """Render without rounding or silently guessing the zone of a naive value.

    Date-only TODOs are historically stored as naive midnight; callers must
    opt into that convention. Events/reminders never opt in. Offsets remain
    legible alongside IANA zones, including both sides of a DST fold.
    Invalid/unresolvable input is retained, not repaired by presentation.
    """
    original = str(value)
    if isinstance(value, str):
        # datetime.fromisoformat silently truncates sub-microsecond precision.
        # Keep such historical/unexpected values verbatim rather than suggest
        # a different instant in a confirmation block.
        if re.search(r"[.,]\d{7,}", value):
            return original
        try:
            if allow_date and _DATE.fullmatch(value):
                return date.fromisoformat(value).isoformat()
            parsed = datetime.fromisoformat(value)
        except ValueError:
            return original
    elif isinstance(value, datetime):
        parsed = value
    else:
        if allow_date:
            return value.isoformat()
        parsed = datetime.combine(value, time.min)

    if naive_midnight_is_date and parsed.tzinfo is None and parsed.time() == time.min:
        return parsed.date().isoformat()
    if tz is not None:
        try:
            parsed = to_utc(parsed, tz).astimezone(tz)
        except AmbiguousOrNonExistentTimeError:
            return f"{original} (hora local ambigua o inexistente en {tz.key})"
        except (OverflowError, ValueError):
            return original

    precision = "microseconds" if parsed.microsecond else "seconds" if parsed.second else "minutes"
    text = parsed.replace(tzinfo=None).isoformat(sep=" ", timespec=precision)
    offset = parsed.utcoffset()
    if offset is None:
        return f"{text} (sin zona horaria)"
    if offset.microseconds:
        return original  # Do not silently truncate an unusual fractional UTC offset.
    seconds = int(offset.total_seconds())
    hours, remainder = divmod(abs(seconds), 3600)
    minutes, seconds_part = divmod(remainder, 60)
    offset_text = f"UTC{'+' if seconds >= 0 else '-'}{hours:02}:{minutes:02}"
    if seconds_part:
        offset_text += f":{seconds_part:02}"
    zone = f"{tz.key}, " if tz is not None else ""
    return f"{text} ({zone}{offset_text})"
