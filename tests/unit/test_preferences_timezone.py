"""Unit tests for src.domain.preferences.timezone (specs/023 T5.2)."""

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest

from src.domain.preferences.timezone import (
    AmbiguousOrNonExistentTimeError,
    resolve_user_timezone,
    to_utc,
)
from src.security.user_context import UserContext

MADRID = ZoneInfo("Europe/Madrid")


class TestResolveUserTimezone:
    def test_returns_fixed_timezone_regardless_of_user(self):
        """T5.1: single fixed timezone for now, same for every user_context."""
        assert resolve_user_timezone(UserContext(user_id="alice")).key == "Europe/Madrid"
        assert resolve_user_timezone(UserContext(user_id="bob")).key == "Europe/Madrid"


class TestToUtc:
    def test_naive_in_summer_dst_converts_to_utc_plus_2(self):
        # Europe/Madrid is CEST (UTC+2) in August.
        naive = datetime(2026, 8, 28, 17, 0)
        result = to_utc(naive, MADRID)
        assert result == datetime(2026, 8, 28, 15, 0, tzinfo=UTC)

    def test_naive_in_winter_converts_to_utc_plus_1(self):
        # Europe/Madrid is CET (UTC+1) in January.
        naive = datetime(2026, 1, 15, 17, 0)
        result = to_utc(naive, MADRID)
        assert result == datetime(2026, 1, 15, 16, 0, tzinfo=UTC)

    def test_aware_value_passed_through_as_utc(self):
        aware = datetime(2026, 8, 28, 15, 0, tzinfo=UTC)
        result = to_utc(aware, MADRID)
        assert result == aware

    def test_aware_non_utc_value_converted(self):
        other_tz = ZoneInfo("America/New_York")
        aware = datetime(2026, 8, 28, 11, 0, tzinfo=other_tz)
        result = to_utc(aware, MADRID)
        assert result == aware.astimezone(UTC)

    def test_ambiguous_dst_fallback_rejected(self):
        """Clocks go back in Europe/Madrid on 2026-10-25 03:00 -> 02:00 CET.

        02:30 occurs twice (CEST and CET) — ambiguous, must be rejected.
        """
        with pytest.raises(AmbiguousOrNonExistentTimeError):
            to_utc(datetime(2026, 10, 25, 2, 30), MADRID)

    def test_nonexistent_dst_gap_rejected(self):
        """Clocks go forward in Europe/Madrid on 2026-03-29 02:00 -> 03:00 CEST.

        02:30 never occurs — nonexistent, must be rejected.
        """
        with pytest.raises(AmbiguousOrNonExistentTimeError):
            to_utc(datetime(2026, 3, 29, 2, 30), MADRID)

    def test_time_just_before_fall_back_gap_is_unambiguous(self):
        # Sanity check: times outside the transition window convert cleanly.
        result = to_utc(datetime(2026, 10, 25, 1, 30), MADRID)
        assert result == datetime(2026, 10, 24, 23, 30, tzinfo=UTC)
