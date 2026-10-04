"""Unit tests for deterministic maintenance amount parsing."""

from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest

from src.domain.vehicles.models import VehicleMaintenanceCreate
from src.domain.vehicles.money import parse_legacy_money


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("286,40 €", (Decimal("286.40"), "EUR")),
        ("$129.99", (Decimal("129.99"), "USD")),
        ("USD 1,299.50", (Decimal("1299.50"), "USD")),
    ],
)
def test_parse_legacy_money_with_explicit_currency(raw: str, expected: tuple[Decimal, str]) -> None:
    assert parse_legacy_money(raw) == expected


@pytest.mark.parametrize("raw", ["286.40", "EUR $129.99", "-1 EUR", "EUR nope"])
def test_parse_legacy_money_rejects_ambiguous_or_invalid_values(raw: str) -> None:
    with pytest.raises(ValueError):
        parse_legacy_money(raw)


def test_new_maintenance_requires_amount_and_currency_together() -> None:
    with pytest.raises(ValueError):
        VehicleMaintenanceCreate(
            vehicle_id=uuid4(),
            date=date(2026, 1, 1),
            description="Aceite",
            cost_amount=Decimal("1"),
        )
