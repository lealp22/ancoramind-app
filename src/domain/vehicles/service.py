"""Vehicle domain service — business logic for vehicles and maintenance.

Framework-independent. Handles resolution, history, and governance.
"""

from datetime import date
from uuid import UUID

from src.domain.vehicles.models import (
    Vehicle,
    VehicleCreate,
    VehicleMaintenance,
    VehicleMaintenanceCreate,
    VehicleResolution,
    VehicleSummary,
)
from src.repositories.maintenance import MaintenanceRepository
from src.repositories.vehicles import VehiclesRepository
from src.security.user_context import UserContext


class VehicleService:
    """Service for managing vehicles and maintenance records."""

    def __init__(
        self,
        vehicles_repo: VehiclesRepository,
        maintenance_repo: MaintenanceRepository,
    ):
        self._vehicles = vehicles_repo
        self._maintenance = maintenance_repo

    # ── Resolution ─────────────────────────────────────

    async def find_vehicle(
        self, user_context: UserContext, reference: str | None
    ) -> VehicleResolution:
        """Resolve a vehicle reference to a specific vehicle.

        Handles: "mi coche", "el Ford", "el Mondeo", "1234ABC" (plate), or None (first vehicle).
        """
        if reference:
            candidates = await self._vehicles.find_by_reference(
                user_context.user_id, reference
            )
        else:
            candidates = await self._vehicles.list_by_user(user_context.user_id)

        if not candidates:
            return VehicleResolution(
                status="not_found",
                message=(
                    f"No encontré ningún vehículo"
                    + (f' que coincida con "{reference}".' if reference else ".")
                    + " Puedes registrar uno con los datos del vehículo."
                ),
            )

        if len(candidates) == 1:
            return VehicleResolution(
                status="found",
                vehicle=candidates[0],
                message=f"Vehículo encontrado: {candidates[0].display_name}",
            )

        return VehicleResolution(
            status="ambiguous",
            candidates=candidates,
            message=(
                f"Encontré {len(candidates)} vehículos que coinciden"
                + (f' con "{reference}"' if reference else "")
                + ". ¿A cuál te refieres?"
            ),
        )

    async def get_summary(
        self, user_context: UserContext, vehicle_id: UUID
    ) -> VehicleSummary | None:
        """Get a vehicle summary with last maintenance and count."""
        vehicle = await self._vehicles.get_by_id(user_context.user_id, vehicle_id)
        if not vehicle:
            return None
        last = await self._maintenance.get_last(user_context.user_id, vehicle_id)
        history = await self._maintenance.get_history(user_context.user_id, vehicle_id)
        return VehicleSummary(
            vehicle=vehicle,
            last_maintenance=last,
            total_maintenance_count=len(history),
        )

    async def get_vehicle(
        self, user_context: UserContext, vehicle_id: UUID
    ) -> Vehicle | None:
        """Get a vehicle by ID, scoped to the user. Returns None if not owned."""
        return await self._vehicles.get_by_id(user_context.user_id, vehicle_id)

    async def get_maintenance_history(
        self, user_context: UserContext, vehicle_id: UUID
    ) -> list[VehicleMaintenance]:
        """Get all maintenance records for a vehicle."""
        # Verify vehicle belongs to user
        vehicle = await self._vehicles.get_by_id(user_context.user_id, vehicle_id)
        if not vehicle:
            return []
        return await self._maintenance.get_history(user_context.user_id, vehicle_id)

    # ── Write Operations ───────────────────────────────

    async def register_maintenance(
        self,
        user_context: UserContext,
        vehicle_id: UUID,
        maintenance_date: date,
        description: str,
        mileage_km: int | None = None,
        workshop: str | None = None,
        cost: str | None = None,
        work_performed: list[str] | None = None,
        notes: str | None = None,
        source_document_id: UUID | None = None,
    ) -> VehicleMaintenance:
        """Register a maintenance event for a vehicle.

        This is a WRITE operation. Caller must handle confirmation/authorization.
        """
        data = VehicleMaintenanceCreate(
            vehicle_id=vehicle_id,
            date=maintenance_date,
            mileage_km=mileage_km,
            description=description,
            workshop=workshop,
            cost=cost,
            work_performed=work_performed or [],
            notes=notes,
            source_document_id=source_document_id,
        )
        return await self._maintenance.create(user_context.user_id, data)