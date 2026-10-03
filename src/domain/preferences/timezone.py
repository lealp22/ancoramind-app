"""User timezone resolution — single chokepoint for `Settings.user_timezone`.

specs/023 T5.1 decision: one fixed IANA timezone for the whole app for now
(``Settings.user_timezone``, default ``"Europe/Madrid"``), but no other module
reads that setting directly — everything goes through
:func:`resolve_user_timezone`. The day per-user timezone configuration exists
(e.g. a ``ancora.user_preferences`` table keyed by ``user_context.user_id``),
only this function changes; tools and services calling it stay the same.
"""

from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from src.config import Settings
from src.security.user_context import UserContext


class AmbiguousOrNonExistentTimeError(ValueError):
    """A naive local datetime does not map to exactly one UTC instant.

    Raised instead of silently picking an interpretation when the wall-clock
    time falls in a DST fold (ambiguous — e.g. 02:30 the night clocks go
    back) or gap (nonexistent — e.g. 02:30 the night clocks go forward).
    """


def resolve_user_timezone(user_context: UserContext) -> ZoneInfo:
    """Resolve the IANA timezone used to interpret/display a user's local times.

    Ignores ``user_context`` today — every user shares the fixed
    ``Settings.user_timezone`` (T5.1). Kept as a parameter so every call site
    already passes the trusted identity and needs no change when per-user
    timezones land.
    """
    del user_context  # unused until per-user preferences exist (T5.1)
    return ZoneInfo(Settings().user_timezone)


def to_utc(value: datetime, tz: ZoneInfo) -> datetime:
    """Normalize ``value`` to an aware UTC datetime.

    An already timezone-aware ``value`` is converted as-is (whatever offset
    it carries). A naive ``value`` is assumed to be local wall-clock time in
    ``tz`` and localized before conversion.

    Raises:
        AmbiguousOrNonExistentTimeError: if a naive ``value`` is ambiguous or
            nonexistent in ``tz`` because of a DST transition.
    """
    if value.tzinfo is not None:
        return value.astimezone(UTC)

    # PEP 495: `fold` disambiguates repeated wall-clock times. If both folds
    # resolve to the same UTC instant, the time isn't ambiguous.
    utc_fold0 = value.replace(tzinfo=tz, fold=0).astimezone(UTC)
    utc_fold1 = value.replace(tzinfo=tz, fold=1).astimezone(UTC)
    if utc_fold0 != utc_fold1:
        raise AmbiguousOrNonExistentTimeError(
            f"La hora {value.isoformat()} es ambigua en {tz.key} "
            "(coincide con el cambio de horario de verano/invierno). "
            "Especifica un offset UTC explícito."
        )

    # A gap (spring-forward) doesn't raise via fold alone: converting back
    # to local time lands on a different wall-clock than the one requested,
    # which is how we detect the wall-clock never existed.
    roundtrip = utc_fold0.astimezone(tz).replace(tzinfo=None)
    if roundtrip != value:
        raise AmbiguousOrNonExistentTimeError(
            f"La hora {value.isoformat()} no existe en {tz.key} "
            "(cae en el cambio de horario de verano/invierno). "
            "Especifica un offset UTC explícito u otra hora."
        )

    return utc_fold0


def to_local_display(value: datetime, tz: ZoneInfo) -> datetime:
    """Convert a persisted datetime to ``tz`` for showing it back to the user.

    ``value`` is expected to be timezone-aware (as returned by the
    ``TIMESTAMPTZ`` columns via asyncpg — always UTC in practice). A naive
    ``value`` is treated as UTC defensively rather than assumed to be in the
    system's local timezone.
    """
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(tz)
