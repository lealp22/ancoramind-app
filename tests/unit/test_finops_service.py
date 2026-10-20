"""Unit tests for the FinOps service (specs/043 T1/T3)."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from src.domain.finops.models import (
    CostTotals,
    LatencyStats,
    ProposalOutcome,
    UserCost,
)
from src.domain.finops.service import (
    FinopsService,
    InvalidWindowError,
    budget_status,
    proposal_rates,
    pseudonymise_user,
    validate_window,
    window_start,
)

SINCE = datetime(2026, 10, 1, tzinfo=UTC)


def test_pseudonym_is_stable_distinct_and_hides_the_id() -> None:
    first = pseudonymise_user("k", "123456789")
    assert first == pseudonymise_user("k", "123456789")
    assert first != pseudonymise_user("k", "123456780")
    assert first != pseudonymise_user("other", "123456789")
    assert first.startswith("u-") and len(first) == 10
    assert "123456789" not in first


@pytest.mark.parametrize("days", [1, 30, 90])
def test_window_accepts_approved_range(days: int) -> None:
    assert validate_window(days) == days


@pytest.mark.parametrize("days", [0, -1, 91, True])
def test_window_rejects_out_of_range(days: int) -> None:
    with pytest.raises(InvalidWindowError):
        validate_window(days)


def test_proposal_rates_ignore_pending_and_handle_empty() -> None:
    empty = proposal_rates([])
    assert empty.resolved == 0 and empty.executed_rate is None
    rates = proposal_rates(
        [
            ProposalOutcome(tool_name="a", status="executed", consent_mode="x", count=6),
            ProposalOutcome(tool_name="b", status="discarded", consent_mode="x", count=2),
            ProposalOutcome(tool_name="c", status="expired", consent_mode="x", count=2),
            ProposalOutcome(
                tool_name="d", status="pending_confirmation", consent_mode="x", count=9
            ),
        ]
    )
    assert rates.resolved == 10
    assert rates.executed_rate == 0.6
    assert rates.discarded_rate == 0.2


def test_budget_is_none_without_governance_and_computes_pct() -> None:
    assert budget_status(1.0, 0.1, None, None) is None
    status = budget_status(5.0, 0.5, 10.0, None)
    assert status is not None
    assert status.month_used_pct == 50.0
    assert status.day_used_pct is None


def _reader() -> AsyncMock:
    reader = AsyncMock()
    reader.totals.return_value = CostTotals(cost_usd=1.0, calls=2)
    reader.daily.return_value = []
    reader.by_user.return_value = [
        ("42", UserCost(user="", cost_usd=1.0, total_tokens=3, calls=2, interactions=1))
    ]
    reader.by_route_model.return_value = []
    reader.by_cost_source.return_value = []
    reader.interactions_by_status.return_value = []
    reader.tool_calls_total.return_value = 0
    reader.proposals.return_value = []
    reader.latency.return_value = LatencyStats()
    return reader


async def test_report_pseudonymises_users_and_never_exposes_the_id() -> None:
    service = FinopsService(_reader(), pseudonym_key="secret")
    report = await service.finops_report(SINCE, 30)
    assert report.by_user[0].user == pseudonymise_user("secret", "42")
    assert '"42"' not in report.model_dump_json()


async def test_reports_reject_invalid_window_without_reading() -> None:
    reader = _reader()
    service = FinopsService(reader, pseudonym_key="secret")
    with pytest.raises(InvalidWindowError):
        await service.finops_report(SINCE, 0)
    with pytest.raises(InvalidWindowError):
        await service.quality_report(SINCE, 91)
    reader.totals.assert_not_called()
    reader.proposals.assert_not_called()


def test_service_requires_a_pseudonym_key() -> None:
    with pytest.raises(ValueError):
        FinopsService(_reader(), pseudonym_key="")


def test_window_start_is_utc_midnight_of_the_oldest_day() -> None:
    now = datetime(2026, 10, 20, 15, 30, tzinfo=UTC)
    assert window_start(now, 1) == datetime(2026, 10, 20, tzinfo=UTC)
    assert window_start(now, 30) == datetime(2026, 9, 21, tzinfo=UTC)
    with pytest.raises(InvalidWindowError):
        window_start(now, 91)
