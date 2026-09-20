"""Unit tests for document extraction schemas."""

from datetime import date

import pytest
from agno.utils.models.schema_utils import get_response_schema_for_provider

from src.domain.documents.schemas import (
    DocumentAmount,
    GenericDocumentExtraction,
    VehicleInvoiceExtraction,
)


class TestGenericDocumentExtraction:
    def test_minimal(self):
        ext = GenericDocumentExtraction()
        assert ext.document_type == "generic"
        assert ext.summary == ""
        assert ext.entities == []
        assert ext.suggested_actions == []

    def test_full(self):
        ext = GenericDocumentExtraction(
            document_type="invoice",
            summary="Reparacion coche",
            document_date=date(2026, 8, 12),
            entities=["Taller Martinez"],
            amounts=[DocumentAmount(description="Total", amount="286,40 EUR")],
            suggested_actions=["register_vehicle_maintenance"],
            confidence=0.85,
        )
        assert ext.document_type == "invoice"
        assert ext.confidence == 0.85
        assert len(ext.amounts) == 1
        assert ext.amounts[0].description == "Total"

    def test_confidence_range(self):
        ext = GenericDocumentExtraction(confidence=0.0)
        assert ext.confidence == 0.0
        ext = GenericDocumentExtraction(confidence=1.0)
        assert ext.confidence == 1.0

    def test_openai_strict_schema_is_closed_and_requires_every_declared_field(self):
        """Regression for the production vision response_format rejection.

        Agno serializes ``output_schema`` through this OpenAI-compatible
        normalizer before it reaches LiteLLM/OpenRouter. Every object must be
        closed and its ``required`` array must exactly match its properties;
        arbitrary ``dict[str, str]`` fields violate that provider contract.
        """
        schema = get_response_schema_for_provider(GenericDocumentExtraction, "openai")

        assert schema["additionalProperties"] is False
        assert set(schema["required"]) == set(schema["properties"])

        amount_schema = schema["$defs"]["DocumentAmount"]
        assert amount_schema["additionalProperties"] is False
        assert set(amount_schema["required"]) == set(amount_schema["properties"])

    def test_rejects_unknown_amount_keys(self):
        with pytest.raises(ValueError):
            GenericDocumentExtraction(
                amounts=[{"description": "Total", "amount": "20 EUR", "unexpected": "no"}]
            )

        ext = GenericDocumentExtraction(amounts=[{"description": "Total", "amount": "20 EUR"}])
        assert ext.amounts == [DocumentAmount(description="Total", amount="20 EUR")]


class TestVehicleInvoiceExtraction:
    def test_full(self):
        ext = VehicleInvoiceExtraction(
            summary="Cambio de aceite",
            invoice_date=date(2026, 8, 12),
            workshop_name="Taller Martinez",
            vehicle_registration="1234ABC",
            vehicle_make_model="Ford Mondeo",
            mileage_km=124350,
            total_amount="286,40 EUR",
            work_performed=["Cambio de aceite", "Cambio de filtro"],
            recommendations=["Proxima revision en 15.000 km"],
            suggested_actions=["register_vehicle_maintenance"],
            confidence=0.92,
        )
        assert ext.vehicle_make_model == "Ford Mondeo"
        assert ext.mileage_km == 124350
        assert len(ext.work_performed) == 2
