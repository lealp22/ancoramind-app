"""Unit tests for document extraction schemas."""

from datetime import date

from src.domain.documents.schemas import GenericDocumentExtraction, VehicleInvoiceExtraction


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
            amounts=[{"desc": "Total", "amount": "286,40 EUR"}],
            suggested_actions=["register_vehicle_maintenance"],
            confidence=0.85,
        )
        assert ext.document_type == "invoice"
        assert ext.confidence == 0.85
        assert len(ext.amounts) == 1

    def test_confidence_range(self):
        ext = GenericDocumentExtraction(confidence=0.0)
        assert ext.confidence == 0.0
        ext = GenericDocumentExtraction(confidence=1.0)
        assert ext.confidence == 1.0


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
