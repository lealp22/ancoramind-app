"""Deterministic parsing and formatting for maintenance monetary amounts."""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

_SYMBOL_CURRENCIES = {"€": "EUR", "$": "USD", "£": "GBP"}
_CODE_PATTERN = re.compile(r"\b(EUR|USD|GBP)\b", re.IGNORECASE)


def parse_legacy_money(value: str | None) -> tuple[Decimal, str] | None:
    """Parse a historical display amount only when its currency is explicit.

    This compatibility parser is intentionally narrow. It supports the formats
    stored by the old maintenance proposal tool (for example ``286,40 €`` or
    ``USD 129.99``) and refuses an amount whose currency cannot be known.
    """
    if value is None or not value.strip():
        return None
    raw = value.strip().upper()
    currencies = {code for symbol, code in _SYMBOL_CURRENCIES.items() if symbol in value}
    currencies.update(match.group(1).upper() for match in _CODE_PATTERN.finditer(raw))
    if len(currencies) != 1:
        raise ValueError("legacy cost must carry exactly one explicit currency")
    numeric = _CODE_PATTERN.sub("", raw)
    for symbol in _SYMBOL_CURRENCIES:
        numeric = numeric.replace(symbol, "")
    numeric = numeric.strip().replace(" ", "")
    if numeric.count(",") and numeric.count("."):
        if numeric.rfind(",") > numeric.rfind("."):
            numeric = numeric.replace(".", "").replace(",", ".")
        else:
            numeric = numeric.replace(",", "")
    else:
        numeric = numeric.replace(",", ".")
    try:
        amount = Decimal(numeric).quantize(Decimal("0.01"))
    except InvalidOperation as exc:
        raise ValueError("legacy cost is not a valid decimal amount") from exc
    if amount < 0:
        raise ValueError("legacy cost must not be negative")
    return amount, currencies.pop()


def format_money(amount: Decimal | None, currency: str | None) -> str | None:
    """Render one already-validated canonical monetary amount for a tool reply."""
    if amount is None or currency is None:
        return None
    return f"{amount:.2f} {currency}"
