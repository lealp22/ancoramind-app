"""BL-55: presentation keeps instants, midnight, DST and significant precision."""

from copy import deepcopy
from datetime import UTC, date, datetime
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest

from src.domain.actions.models import payload_hash
from src.domain.actions.presentation import render_proposal_block
from src.domain.preferences.display import format_temporal

MADRID = ZoneInfo("Europe/Madrid")


@pytest.mark.parametrize(
    "value,expected",
    [
        ("2026-11-01", "2026-11-01"),
        (date(2026, 11, 1), "2026-11-01"),
        ("2026-11-01T10:00:00+01:00", "2026-11-01 10:00 (Europe/Madrid, UTC+01:00)"),
        ("2026-11-01T09:00:00Z", "2026-11-01 10:00 (Europe/Madrid, UTC+01:00)"),
        ("2026-11-01T10:00:00-03:00", "2026-11-01 14:00 (Europe/Madrid, UTC+01:00)"),
        ("2026-07-01T00:00:00+02:00", "2026-07-01 00:00 (Europe/Madrid, UTC+02:00)"),
        ("2026-11-01T10:00:01.000123Z", "2026-11-01 11:00:01.000123 (Europe/Madrid, UTC+01:00)"),
        (datetime(2026, 11, 1, 9, tzinfo=UTC), "2026-11-01 10:00 (Europe/Madrid, UTC+01:00)"),
        ("2026-10-25T00:30:00Z", "2026-10-25 02:30 (Europe/Madrid, UTC+02:00)"),
        ("2026-10-25T01:30:00Z", "2026-10-25 02:30 (Europe/Madrid, UTC+01:00)"),
        ("2026-03-29T00:30:00Z", "2026-03-29 01:30 (Europe/Madrid, UTC+01:00)"),
        ("2026-03-29T01:30:00Z", "2026-03-29 03:30 (Europe/Madrid, UTC+02:00)"),
        ("2026-11-01T10:00:00", "2026-11-01 10:00 (Europe/Madrid, UTC+01:00)"),
        ("invalid", "invalid"),
    ],
)
def test_display(value, expected):
    assert format_temporal(value, MADRID) == expected


@pytest.mark.parametrize("value", ["2026-10-25T02:30:00", "2026-03-29T02:30:00"])
def test_ambiguous_or_nonexistent_naive_time_is_not_repaired(value):
    assert format_temporal(value, MADRID) == (
        f"{value} (hora local ambigua o inexistente en Europe/Madrid)"
    )


def test_missing_zone_is_not_assumed_utc():
    assert format_temporal("2026-11-01T00:00:00") == ("2026-11-01 00:00 (sin zona horaria)")


@pytest.mark.parametrize(
    "tool,key",
    [
        ("create_calendar_event", "start_at"),
        ("create_reminder", "trigger_at"),
    ],
)
def test_core_dates_are_user_local_without_mutation(tool, key):
    payload = {key: "2026-11-01T09:00:01.000123Z", "title": "Ensayo"}
    before = deepcopy(payload)
    digest = payload_hash(tool, payload)
    block = render_proposal_block(uuid4(), tool, payload, timezone=MADRID)
    assert "2026-11-01 10:00:01.000123 (Europe/Madrid, UTC+01:00)" in block
    assert payload == before
    assert payload_hash(tool, payload) == digest


def test_todo_date_convention_is_explicit_and_does_not_apply_to_reminders():
    value = "2026-11-01T00:00:00"
    assert format_temporal(value, MADRID, naive_midnight_is_date=True) == "2026-11-01"
    assert "00:00" in format_temporal(value, MADRID, allow_date=False)


@pytest.mark.parametrize("value", [
    "2026-11-01T10:00:01.1234567Z", "2026-11-01T10:00:01+01:00:00.5",
    "0001-01-01T00:00:00+14:00",
])
def test_unrepresentable_precision_or_conversion_keeps_original(value):
    # Check the fractional offset without conversion too: conversion may
    # produce a perfectly representable local instant, which is also lossless.
    tz = None if "+01:00:00.5" in value else MADRID
    assert format_temporal(value, tz) == value
