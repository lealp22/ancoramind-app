"""Register vehicle maintenance — WRITE tools with action proposal pattern.

These tools require confirmation per governance policy.
"""

from datetime import date
from uuid import UUID

from agno.run import RunContext

from src.domain.vehicles.service import VehicleService
from src.repositories.actions import ActionProposalsRepository
from src.repositories.database import get_session
from src.repositories.maintenance import MaintenanceRepository
from src.repositories.vehicles import VehiclesRepository
from src.security.user_context import UserContext


async def _get_vehicle_service():
    session = await get_session()
    return VehicleService(VehiclesRepository(session), MaintenanceRepository(session))


async def _get_actions_repo():
    session = await get_session()
    return ActionProposalsRepository(session)


async def propose_vehicle_maintenance(
    run_context: RunContext,
    vehicle_id: str,
    date_str: str,
    description: str,
    mileage_km: int | None = None,
    workshop: str | None = None,
    cost: str | None = None,
    work_performed: str | None = None,
    notes: str | None = None,
    source_document_id: str | None = None,
) -> str:
    """PROPOSE a vehicle maintenance record — requires user confirmation.

    Creates an action proposal. Does NOT write yet.
    Use when user wants to record maintenance, or after invoice analysis.

    Args:
        run_context: Injected by Agno.
        vehicle_id: UUID of the vehicle.
        date_str: Date in YYYY-MM-DD format.
        description: Maintenance description.
        mileage_km: Optional mileage.
        workshop: Optional workshop name.
        cost: Optional cost (e.g. '286,40 €').
        work_performed: Optional comma-separated work items.
        notes: Optional notes.
        source_document_id: Optional source document UUID.
    """
    user_ctx = UserContext.from_run_context(run_context)
    try:
        vid = UUID(vehicle_id)
    except ValueError:
        return f"ID de vehículo no válido: {vehicle_id}"

    try:
        date.fromisoformat(date_str)
    except ValueError:
        return f"Fecha no válida: {date_str}. Usa YYYY-MM-DD."

    work_items = [w.strip() for w in (work_performed or "").split(",") if w.strip()]

    # Verify vehicle belongs to user
    service = await _get_vehicle_service()
    target = await service.get_vehicle(user_ctx, vid)
    if not target:
        return f"Vehículo no encontrado: {vehicle_id}"

    # Create action proposal
    src_doc = UUID(source_document_id) if source_document_id else None
    actions_repo = await _get_actions_repo()
    proposal = await actions_repo.create(
        user_id=user_ctx.user_id,
        tool_name="register_vehicle_maintenance",
        payload={
            "vehicle_id": str(vid), "date": date_str, "description": description,
            "mileage_km": mileage_km, "workshop": workshop, "cost": cost,
            "work_performed": work_items, "notes": notes,
            "source_document_id": str(src_doc) if src_doc else None,
        },
        source_document_id=src_doc,
    )

    lines = [
        f"📋 **Propuesta de mantenimiento** (`{proposal['id']}`)",
        f"   Vehículo: {target.display_name}",
        f"   Fecha: {date_str}",
    ]
    if mileage_km:
        lines.append(f"   Kilometraje: {mileage_km:,} km")
    lines.append(f"   {description}")
    if workshop:
        lines.append(f"   Taller: {workshop}")
    if cost:
        lines.append(f"   Importe: {cost}")
    if work_items:
        lines.append(f"   Trabajos: {', '.join(work_items)}")
    lines.append("\n¿Confirmas el registro de este mantenimiento?")
    return "\n".join(lines)


async def execute_vehicle_maintenance(run_context: RunContext, proposal_id: str) -> str:
    """Execute a confirmed vehicle maintenance proposal.

    Only call after user explicitly confirmed (e.g. 'Sí' after a proposal).

    Args:
        run_context: Injected by Agno.
        proposal_id: The proposal ID from propose_vehicle_maintenance.
    """
    user_ctx = UserContext.from_run_context(run_context)
    actions_repo = await _get_actions_repo()
    proposal = await actions_repo.confirm(user_ctx.user_id, proposal_id)
    if not proposal:
        return f"No se encontró la propuesta `{proposal_id}` o ya no está pendiente."

    payload = proposal["payload"]
    service = await _get_vehicle_service()
    try:
        record = await service.register_maintenance(
            user_context=user_ctx,
            vehicle_id=UUID(payload["vehicle_id"]),
            maintenance_date=date.fromisoformat(payload["date"]),
            description=payload["description"],
            mileage_km=payload.get("mileage_km"),
            workshop=payload.get("workshop"),
            cost=payload.get("cost"),
            work_performed=payload.get("work_performed", []),
            notes=payload.get("notes"),
            source_document_id=UUID(payload["source_document_id"])
            if payload.get("source_document_id") else None,
        )
        await actions_repo.mark_executed(user_ctx.user_id, proposal_id)

        lines = [
            "✅ **Mantenimiento registrado**",
            f"   Fecha: {record.date} — {record.description}",
        ]
        if record.cost:
            lines.append(f"   Importe: {record.cost}")
        lines.append(f"   ID: `{record.id}`")
        if payload.get("source_document_id"):
            lines.append(f"   Documento origen: `{payload['source_document_id']}`")
        return "\n".join(lines)
    except Exception as e:
        return f"❌ Error al registrar: {str(e)[:200]}"
