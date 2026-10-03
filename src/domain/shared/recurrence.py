"""Simple structured recurrence rule + pure expansion functions.

Deliberately NOT RRULE/iCal (RFC 5545): there is no real external calendar
provider integrated today (``NoopCalendarProvider``), so that complexity and
dependency are not justified (specs/024). Pure domain logic — no Agno, no
SQL, no I/O — shared by the calendar domain (virtual expansion at read time)
and the reminders domain (materializing the next pending row on fire).
"""

from __future__ import annotations

import calendar as _calendar
import json
from datetime import datetime, timedelta
from enum import StrEnum

from pydantic import BaseModel, Field, model_validator


class RecurrenceFrequency(StrEnum):
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    YEARLY = "yearly"


class RecurrenceRule(BaseModel):
    """A simple recurrence rule: frequency + interval + optional end bound."""

    frequency: RecurrenceFrequency
    interval: int = Field(default=1, ge=1, le=365)
    until: datetime | None = None

    @model_validator(mode="after")
    def _until_must_be_aware(self) -> RecurrenceRule:
        if self.until is not None and self.until.tzinfo is None:
            raise ValueError("recurrence_rule.until debe ser timezone-aware")
        return self


def _add_months(anchor_day: int, dt: datetime, months: int) -> datetime:
    """Return `dt` shifted by `months`, with the day clamped to `anchor_day`.

    Clamping always uses the *anchor's* original day-of-month, never `dt`'s
    own (possibly already-clamped) day — otherwise a Jan 31 anchor would
    permanently degrade to the 28th after passing through February instead
    of returning to the 31st in March.
    """
    total = dt.month - 1 + months
    year = dt.year + total // 12
    month = total % 12 + 1
    last_day_of_month = _calendar.monthrange(year, month)[1]
    day = min(anchor_day, last_day_of_month)
    return dt.replace(year=year, month=month, day=day)


def next_occurrence(
    rule: RecurrenceRule, anchor: datetime, after: datetime
) -> datetime | None:
    """Compute the occurrence immediately following `after` on this rule.

    `anchor` is the chain's original occurrence (the first created event or
    reminder) — its day-of-month/year is what monthly/yearly clamping always
    derives from, regardless of how many steps `after` already is from it.
    Returns `None` once the computed occurrence would be after `rule.until`
    (inclusive bound: an occurrence equal to `until` is still valid; the
    occurrence after it is not).
    """
    if rule.frequency is RecurrenceFrequency.DAILY:
        candidate = after + timedelta(days=rule.interval)
    elif rule.frequency is RecurrenceFrequency.WEEKLY:
        candidate = after + timedelta(weeks=rule.interval)
    elif rule.frequency is RecurrenceFrequency.MONTHLY:
        candidate = _step_monthly(rule, anchor, after, months_per_step=1)
    else:  # YEARLY
        candidate = _step_monthly(rule, anchor, after, months_per_step=12)

    if rule.until is not None and candidate > rule.until:
        return None
    return candidate


def _step_monthly(
    rule: RecurrenceRule, anchor: datetime, after: datetime, months_per_step: int
) -> datetime:
    """Smallest anchor-aligned occurrence strictly after `after`."""
    months_elapsed = (after.year - anchor.year) * 12 + (after.month - anchor.month)
    step = rule.interval * months_per_step
    steps_so_far = months_elapsed // step if step else 0
    candidate = _add_months(anchor.day, anchor, steps_so_far * step)
    while candidate <= after:
        steps_so_far += 1
        candidate = _add_months(anchor.day, anchor, steps_so_far * step)
    return candidate


def occurrences_in_range(
    rule: RecurrenceRule,
    anchor_start: datetime,
    range_start: datetime,
    range_end: datetime,
    max_iterations: int = 10_000,
) -> list[datetime]:
    """All occurrence start datetimes within [range_start, range_end].

    Handles `anchor_start` being before `range_start` (e.g. a birthday
    created last year still producing an occurrence this year): walks
    forward from the anchor, skipping occurrences before the range, and
    stops at `range_end` or `rule.until`. The anchor itself counts as the
    first occurrence and is included if it falls in range. Bounded by
    `max_iterations` since this runs on the read path (``check_calendar``).
    """
    occurrences: list[datetime] = []
    current: datetime | None = anchor_start
    iterations = 0
    while current is not None and current <= range_end and iterations < max_iterations:
        if current >= range_start:
            occurrences.append(current)
        current = next_occurrence(rule, anchor=anchor_start, after=current)
        iterations += 1
    return occurrences


def recurrence_rule_from_flat(
    frequency: str | None, interval: int | None, until: str | None
) -> RecurrenceRule | None:
    """Build a `RecurrenceRule` from flat scalar tool-payload keys.

    `frequency` is `None` -> no recurrence (the other two are ignored).
    Raises `ValueError`/`TypeError` on invalid values — callers already
    catch `(KeyError, TypeError, ValueError)` around payload re-parsing.
    """
    if frequency is None:
        return None
    return RecurrenceRule(
        frequency=RecurrenceFrequency(frequency),
        interval=interval if interval is not None else 1,
        until=datetime.fromisoformat(until) if until else None,
    )


def rule_to_jsonb_param(rule: RecurrenceRule | None) -> str | None:
    """Serialize a `RecurrenceRule` for a `CAST(:param AS jsonb)` SQL param."""
    if rule is None:
        return None
    return json.dumps(rule.model_dump(mode="json"))


def recurrence_rule_to_flat(rule: RecurrenceRule | None) -> dict[str, str | int | None]:
    """Inverse of `recurrence_rule_from_flat`, for building propose_* payloads."""
    if rule is None:
        return {"recurrence_frequency": None, "recurrence_interval": None, "recurrence_until": None}
    return {
        "recurrence_frequency": rule.frequency.value,
        "recurrence_interval": rule.interval,
        "recurrence_until": rule.until.isoformat() if rule.until else None,
    }
