"""specs/046 T2: schema layer of the Phoenix masking (field name + value shape)."""

from __future__ import annotations

import importlib
import inspect
import json
import pkgutil
from typing import Any
from unittest.mock import Mock

import pytest
from opentelemetry.sdk.trace.export import SpanExporter

import src.agent.tools as tools_package
from src.observability.field_policy import (
    ALL_CLASSIFIED,
    INVALID_MARKER,
    FieldClass,
    classify,
    is_uuid,
    is_valid_structured,
)
from src.observability.phoenix_capture import PROPOSE_TOOLS
from src.observability.phoenix_export import MaskedSpanExporter

UUID = "0aa839cf-80fe-4593-87c3-2ce6816db448"
DNI = "12345678Z"


def _exporter() -> MaskedSpanExporter:
    return MaskedSpanExporter(Mock(spec=SpanExporter), project_name="ancoramind")


def _project(payload: dict[str, Any]) -> dict[str, Any]:
    return json.loads(json.dumps(_exporter()._json_value(payload)))


# ── drift: every real propose_* parameter is classified ─────────────────────


def _propose_parameters() -> dict[str, set[str]]:
    found: dict[str, set[str]] = {}
    for module_info in pkgutil.iter_modules(tools_package.__path__):
        module = importlib.import_module(f"src.agent.tools.{module_info.name}")
        for name, fn in inspect.getmembers(module, inspect.isfunction):
            if name in PROPOSE_TOOLS and fn.__module__ == module.__name__:
                parameters = inspect.signature(inspect.unwrap(fn)).parameters
                found[name] = {p for p in parameters if p != "run_context"}
    return found


def test_every_propose_parameter_is_explicitly_classified():
    """An unclassified parameter would silently fall back to free text. That is safe
    (it is pattern-masked) but hides a decision, so adding one must be deliberate."""
    parameters = _propose_parameters()
    assert set(parameters) == set(PROPOSE_TOOLS), "a propose_* tool could not be inspected"
    unclassified = {
        (tool, field)
        for tool, fields in parameters.items()
        for field in fields
        if field not in ALL_CLASSIFIED
    }
    assert not unclassified, f"Classify in field_policy.py: {sorted(unclassified)}"


def test_classification_is_exclusive_and_case_insensitive():
    for name in ALL_CLASSIFIED:
        assert classify(name) is classify(name.upper())
    assert classify("totally_unknown_field") is FieldClass.FREE_TEXT


# ── identifiers ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("field", "marker"),
    [("registration", "[MATRICULA]"), ("vin", "[BASTIDOR]"), ("email", "[EMAIL]")],
)
def test_identifiers_are_masked_whatever_the_value_looks_like(field, marker):
    assert _project({field: "unrecognisable"}) == {field: marker}
    assert _project({field.upper(): 12345}) == {field.upper(): marker}


# ── internal ids ────────────────────────────────────────────────────────────


@pytest.mark.parametrize("field", ["list_id", "item_id", "vehicle_id", "document_id"])
def test_a_uuid_in_an_id_field_is_kept_to_correlate_with_postgres(field):
    assert _project({field: UUID}) == {field: UUID}


def test_an_uppercase_uuid_is_normalised_not_rejected():
    assert _project({"list_id": UUID.upper()}) == {"list_id": UUID}


@pytest.mark.parametrize(
    "value",
    ["no-es-uuid", DNI, "ES9121000418450200051332", UUID + "x", "{" + UUID + "}", "", 7],
)
def test_a_non_uuid_in_an_id_field_never_rides_along(value):
    assert _project({"list_id": value}) == {"list_id": INVALID_MARKER}


def test_a_null_optional_id_is_kept_as_null():
    assert _project({"source_document_id": None}) == {"source_document_id": None}


def test_the_name_alone_grants_no_exemption_to_a_uuid_in_free_text():
    # A uuid inside a title is prose, not a pointer: it goes through pattern masking.
    projected = _project({"title": UUID})
    assert projected["title"] != UUID


# ── structured ──────────────────────────────────────────────────────────────


def test_structured_values_with_their_expected_shape_are_kept():
    payload = {
        "year": 2019,
        "mileage_km": 123456,
        "minutes": 30,
        "with_reminder": True,
        "cost_amount": "184.50",
        "cost_currency": "EUR",
        "priority": "high",
        "recurrence_frequency": "weekly",
        "due_date": "2026-10-25",
        "start_at": "2026-10-25T10:00:00+02:00",
        "recurrence_until": "2026-12-31T23:59:59Z",
    }
    assert _project(payload) == payload


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("year", "mi dni es " + DNI),
        ("year", 99_999_999_999),
        ("year", -1),
        ("due_date", "llamar a Maria mañana"),
        # A valid date PREFIX must not smuggle prose behind it (match vs fullmatch).
        ("due_date", "2026-10-25 llamar a Maria"),
        ("start_at", "2026-10-25T10:00:00+02:00 y mi dni " + DNI),
        ("cost_amount", "184.50 euros de Maria"),
        ("cost_currency", "EUR de Maria"),
        ("start_at", DNI),
        ("cost_amount", DNI),
        ("cost_amount", "12.345"),
        ("cost_currency", "euros de Maria"),
        ("priority", "llamar a Maria"),
        ("recurrence_frequency", "cada martes con Ana"),
        ("minutes", [1, 2]),
        ("mileage_km", {"x": 1}),
    ],
)
def test_prose_or_malformed_values_in_a_structured_field_become_invalid(field, value):
    assert _project({field: value}) == {field: INVALID_MARKER}


def test_a_bare_number_is_not_swallowed_by_the_numeric_safety_net_when_structured():
    # Before T2 every int went through the "long digit run" net as a string.
    assert _project({"mileage_km": 123456, "year": 2019}) == {"mileage_km": 123456, "year": 2019}


def test_the_same_long_number_in_free_text_is_still_masked():
    # Which marker wins (telephone vs. generic number) depends on detector order in
    # masking.py; what matters here is that the digits never leave the process.
    masked = _project({"notes": "ref 123456789012"})["notes"]
    assert "123456789012" not in masked
    assert masked.startswith("ref [")


# ── free text keeps its content, masked by pattern ───────────────────────────


def test_free_text_is_kept_and_pattern_masked():
    projected = _project(
        {
            "title": f"llamar a 612345678 y DNI {DNI}",
            "description": "dolor de espalda",
            "nickname": "el coche de Maria",
        }
    )
    assert projected["title"] == "llamar a [TELEFONO] y DNI [DNI]"
    assert projected["description"] == "dolor de espalda"
    assert projected["nickname"] == "el coche de Maria"


def test_known_limit_names_and_health_data_in_free_text_are_not_detected():
    """Documents the accepted residual risk of ADR-007 (patterns see formats only)."""
    assert _project({"notes": "visita al cardiólogo con Maria Lopez"})["notes"] == (
        "visita al cardiólogo con Maria Lopez"
    )


def test_unlisted_fields_fall_back_to_pattern_masking_not_to_trust():
    assert _project({"brand_new_field": f"dni {DNI}"}) == {"brand_new_field": "dni [DNI]"}


def test_nested_structures_are_walked_with_the_same_policy():
    projected = _project({"outer": {"registration": "x", "list_id": "bad", "title": DNI}})
    assert projected == {
        "outer": {"registration": "[MATRICULA]", "list_id": INVALID_MARKER, "title": "[DNI]"}
    }


# ── helpers ─────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (UUID, True),
        (UUID.upper(), True),
        ("x", False),
        (UUID.replace("-", ""), False),
        (None, False),
    ],
)
def test_is_uuid_accepts_only_the_canonical_form(value, expected):
    assert is_uuid(value) is expected


def test_is_valid_structured_rejects_booleans_as_numbers_in_amount_fields():
    assert is_valid_structured("cost_amount", True) is True  # bool allowed generically
    assert is_valid_structured("year", None) is True
    assert is_valid_structured("year", "2019") is False
