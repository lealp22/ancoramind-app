"""Vehicle domain models — vehicles and maintenance records."""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field


class VehicleCreate(BaseModel):
    """Input for creating a vehicle."""

    make: str = Field(
        ..., min_length=1, max_length=100, description="Brand (Ford, Toyota, etc.)"
    )
    model: str = Field(
        ..., min_length=1, max_length=100, description="Model (Mondeo, Corolla, etc.)"
    )
    year: int | None = Field(default=None, ge=1900, le=2100)
    registration: str | None = Field(default=None, description="License plate")
    nickname: str | None = Field(
        default=None, description="User's nickname (mi coche, la furgoneta)"
    )
    vin: str | None = Field(default=None)


class Vehicle(BaseModel):
    """A vehicle owned by a user."""

    id: UUID
    user_id: str
    make: str
    model: str
    year: int | None
    registration: str | None
    nickname: str | None
    vin: str | None
    created_at: datetime

    model_config = {"from_attributes": True}

    @property
    def display_name(self) -> str:
        """Human-readable vehicle name."""
        parts = [self.nickname] if self.nickname else []
        if self.make:
            parts.append(self.make)
        if self.model:
            parts.append(self.model)
        return " ".join(parts) or "Vehículo desconocido"


class VehicleMaintenanceCreate(BaseModel):
    """Input for creating a maintenance record."""

    vehicle_id: UUID
    date: date
    mileage_km: int | None = Field(default=None, ge=0)
    description: str = Field(..., min_length=1, max_length=2000)
    workshop: str | None = None
    cost: str | None = None
    work_performed: list[str] = Field(default_factory=list)
    notes: str | None = None
    source_document_id: UUID | None = Field(
        default=None, description="Source document if from invoice"
    )


class VehicleMaintenance(BaseModel):
    """A maintenance record for a vehicle."""

    id: UUID
    vehicle_id: UUID
    user_id: str
    date: date
    mileage_km: int | None
    description: str
    workshop: str | None
    cost: str | None
    work_performed: list[str]
    notes: str | None
    source_document_id: UUID | None
    created_at: datetime

    model_config = {"from_attributes": True}


class VehicleSummary(BaseModel):
    """Aggregated summary for a vehicle."""

    vehicle: Vehicle
    last_maintenance: VehicleMaintenance | None
    total_maintenance_count: int


class VehicleResolution(BaseModel):
    """Result of resolving a vehicle reference."""

    status: str  # "found" | "not_found" | "ambiguous"
    vehicle: Vehicle | None = None
    candidates: list[Vehicle] = Field(default_factory=list)
    message: str = ""
