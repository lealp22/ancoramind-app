"""Unit tests for the shared recurrence module (src/domain/shared/recurrence.py)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from src.domain.shared.recurrence import (
    RecurrenceFrequency,
    RecurrenceRule,
    next_occurrence,
    occurrences_in_range,
    recurrence_rule_from_flat,
    recurrence_rule_to_flat,
)


def _dt(y: int, m: int, d: int, h: int = 0) -> datetime:
    return datetime(y, m, d, h, tzinfo=UTC)


class TestNextOccurrenceDailyWeekly:
    def test_daily_default_interval(self) -> None:
        rule = RecurrenceRule(frequency=RecurrenceFrequency.DAILY)
        anchor = _dt(2026, 1, 1)
        assert next_occurrence(rule, anchor=anchor, after=anchor) == _dt(2026, 1, 2)

    def test_weekly_interval_two(self) -> None:
        rule = RecurrenceRule(frequency=RecurrenceFrequency.WEEKLY, interval=2)
        anchor = _dt(2026, 1, 1)
        assert next_occurrence(rule, anchor=anchor, after=anchor) == _dt(2026, 1, 15)


class TestMonthlyClampNoDrift:
    def test_jan31_monthly_does_not_drift_after_february(self) -> None:
        rule = RecurrenceRule(frequency=RecurrenceFrequency.MONTHLY)
        anchor = _dt(2026, 1, 31)
        feb = next_occurrence(rule, anchor=anchor, after=anchor)
        assert feb == _dt(2026, 2, 28)
        mar = next_occurrence(rule, anchor=anchor, after=feb)
        assert mar == _dt(2026, 3, 31)  # back to 31, not stuck at 28

    def test_monthly_interval_six(self) -> None:
        rule = RecurrenceRule(frequency=RecurrenceFrequency.MONTHLY, interval=6)
        anchor = _dt(2026, 1, 15)
        assert next_occurrence(rule, anchor=anchor, after=anchor) == _dt(2026, 7, 15)


class TestYearlyClamp:
    def test_leap_day_anchor_clamps_on_non_leap_year(self) -> None:
        rule = RecurrenceRule(frequency=RecurrenceFrequency.YEARLY)
        anchor = _dt(2024, 2, 29)  # 2024 is a leap year
        nxt = next_occurrence(rule, anchor=anchor, after=anchor)
        assert nxt == _dt(2025, 2, 28)
        nxt2 = next_occurrence(rule, anchor=anchor, after=nxt)
        assert nxt2 == _dt(2026, 2, 28)

    def test_yearly_returns_to_leap_day_on_next_leap_year(self) -> None:
        rule = RecurrenceRule(frequency=RecurrenceFrequency.YEARLY)
        anchor = _dt(2024, 2, 29)
        # Walk to 2028 (next leap year) directly from the anchor.
        after = _dt(2027, 2, 28)
        nxt = next_occurrence(rule, anchor=anchor, after=after)
        assert nxt == _dt(2028, 2, 29)


class TestUntilBoundary:
    def test_until_inclusive_boundary(self) -> None:
        anchor = _dt(2026, 1, 1)
        rule = RecurrenceRule(frequency=RecurrenceFrequency.DAILY, until=_dt(2026, 1, 2))
        assert next_occurrence(rule, anchor=anchor, after=anchor) == _dt(2026, 1, 2)
        assert next_occurrence(rule, anchor=anchor, after=_dt(2026, 1, 2)) is None

    def test_naive_until_rejected(self) -> None:
        with pytest.raises(ValueError, match="timezone-aware"):
            RecurrenceRule(frequency=RecurrenceFrequency.DAILY, until=datetime(2026, 1, 1))


class TestOccurrencesInRange:
    def test_anchor_in_past_yields_occurrence_in_current_range(self) -> None:
        rule = RecurrenceRule(frequency=RecurrenceFrequency.YEARLY)
        anchor = _dt(2020, 3, 15)  # birthday created years ago
        occs = occurrences_in_range(rule, anchor, _dt(2026, 1, 1), _dt(2026, 12, 31))
        assert occs == [_dt(2026, 3, 15)]

    def test_anchor_itself_included_when_in_range(self) -> None:
        rule = RecurrenceRule(frequency=RecurrenceFrequency.WEEKLY)
        anchor = _dt(2026, 1, 5)
        occs = occurrences_in_range(rule, anchor, _dt(2026, 1, 1), _dt(2026, 1, 5))
        assert occs == [anchor]

    def test_until_stops_expansion(self) -> None:
        rule = RecurrenceRule(frequency=RecurrenceFrequency.WEEKLY, until=_dt(2026, 1, 15))
        anchor = _dt(2026, 1, 1)
        occs = occurrences_in_range(rule, anchor, _dt(2026, 1, 1), _dt(2026, 2, 1))
        assert occs == [_dt(2026, 1, 1), _dt(2026, 1, 8), _dt(2026, 1, 15)]

    def test_max_iterations_guard(self) -> None:
        rule = RecurrenceRule(frequency=RecurrenceFrequency.DAILY)
        anchor = _dt(2000, 1, 1)
        occs = occurrences_in_range(
            rule, anchor, _dt(2000, 1, 1), _dt(2050, 1, 1), max_iterations=10
        )
        assert len(occs) == 10


class TestFlatRoundTrip:
    def test_round_trip(self) -> None:
        rule = RecurrenceRule(
            frequency=RecurrenceFrequency.MONTHLY, interval=3, until=_dt(2027, 1, 1)
        )
        flat = recurrence_rule_to_flat(rule)
        rebuilt = recurrence_rule_from_flat(
            flat["recurrence_frequency"], flat["recurrence_interval"], flat["recurrence_until"]
        )
        assert rebuilt == rule

    def test_none_frequency_yields_none(self) -> None:
        assert recurrence_rule_from_flat(None, 3, None) is None

    def test_none_rule_to_flat(self) -> None:
        flat = recurrence_rule_to_flat(None)
        assert flat == {
            "recurrence_frequency": None,
            "recurrence_interval": None,
            "recurrence_until": None,
        }

    def test_invalid_frequency_raises(self) -> None:
        with pytest.raises(ValueError):
            recurrence_rule_from_flat("fortnightly", 1, None)
