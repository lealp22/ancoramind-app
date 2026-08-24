"""AI Extraction schemas — Pydantic models for structured document extraction."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field


class GenericDocumentExtraction(BaseModel):
    """Generic extraction for any document type."""

    document_type: str = "generic"
    title: str | None = None
    summary: str = ""
    document_date: date | None = None
    entities: list[str] = Field(default_factory=list)
    amounts: list[dict[str, str]] = Field(default_factory=list)
    suggested_actions: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)


class VehicleInvoiceExtraction(BaseModel):
    """Extraction schema for vehicle workshop/repair invoices."""

    document_type: str = "vehicle_invoice"
    summary: str = ""
    invoice_date: date | None = None
    workshop_name: str | None = None
    vehicle_registration: str | None = None
    vehicle_make_model: str | None = None
    mileage_km: int | None = None
    total_amount: str | None = None
    work_performed: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    suggested_actions: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)