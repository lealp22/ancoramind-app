"""Vehicle tools — thin Agno tool adapters for VehicleService.

All WRITE operations use action proposals for governance.
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


async def find_vehicle(run_context: RunContext, reference: str | None = None) -> str:
    """Find a vehicle by make, model, nickname, or registration.

    Use when the user mentions their vehicle:
    - "mi coche" / "el Ford" / "el Mondeo" / "1234ABC"
    - "¿Qué coches tengo?"

    Args:
        run_context: Injected by Agno.
        reference: Make, model, nickname, or license plate. Omit to list all.
    """
    user_ctx = UserContext.from_run_context(run_context)
    service = await _get_vehicle_service()
    result = await service.find_vehicle(user_ctx, reference)

    if result.status == "found" and result.vehicle:
        v = result.vehicle
        lines = [f"🚗 **{v.display_name}**", f"   ID: `{v.id}`", f"   Marca: {v.make} | Modelo: {v.model}"]
        if v.year:
            lines.append(f"   Año: {v.year}")
        if v.registration:
            lines.append(f"   Matrícula: {v.registration}")
        return "\n".join(lines)

    if result.status == "ambiguous":
        lines = [result.message, ""]
        for i, v in enumerate(result.candidates, 1):
            extra = f" ({v.registration})" if v.registration else ""
            lines.append(f"  {i}. {v.display_name}{extra} — `{v.id}`")
        return "\n".join(lines)

    return result.message


async def get_vehicle_summary(run_context: RunContext, vehicle_id: str) -> str:
    """Get a complete summary of a vehicle including last maintenance.

    Use when the user asks about a specific vehicle's status.
    Use find_vehicle first to get the vehicle_id.

    Args:
        run_context: Injected by Agno.
        vehicle_id: UUID from find_vehicle results.
    """
    user_ctx = UserContext.from_run_context(run_context)
    service = await _get_vehicle_service()

    try:
        vid = UUID(vehicle_id)
    except ValueError:
        return f"ID de vehículo no válido: {vehicle_id}"

    summary = await service.get_summary(user_ctx, vid)
    if not summary:
        return f"Vehículo no encontrado: {vehicle_id}"

    v = summary.vehicle
    lines = [f"🚗 **{v.display_name}**", f"   ID: `{v.id}`", f"   {v.make} {v.model}"
             + (f" ({v.year})" if v.year else "")
             + (f" — {v.registration}" if v.registration else ""),
             f"   Total intervenciones: {summary.total_maintenance_count}"]

    if summary.last_maintenance:
        m = summary.last_maintenance
        lines.append(f"\n🔧 **Último mantenimiento:**")
        lines.append(f"   Fecha: {m.date}")
        if m.mileage_km:
            lines.append(f"   Kilometraje: {m.mileage_km:,} km")
        lines.append(f"   {m.description}")
        if m.workshop:
            lines.append(f"   Taller: {m.workshop}")
        if m.cost:
            lines.append(f"   Importe: {m.cost}")
        if m.work_performed:
            lines.append(f"   Trabajos: {', '.join(m.work_performed)}")
    else:
        lines.append("\n   Sin historial de mantenimiento.")

    return "\n".join(lines)


async def get_vehicle_maintenance_history(run_context: RunContext, vehicle_id: str) -> str:
    """Get the full maintenance history for a vehicle.

    Args:
        run_context: Injected by Agno.
        vehicle_id: UUID from find_vehicle results.
    """
    user_ctx = UserContext.from_run_context(run_context)
    service = await _get_vehicle_service()

    try:
        vid = UUID(vehicle_id)
    except ValueError:
        return f"ID de vehículo no válido: {vehicle_id}"

    records = await service.get_maintenance_history(user_ctx, vid)
    if not records:
        return "No hay registros de mantenimiento para este vehículo."

    lines = [f"🔧 **Historial de mantenimiento** ({len(records)} intervenciones):\n"]
    for m in records:
        km = f" — {m.mileage_km:,} km" if m.mileage_km else ""
        cost = f" — {m.cost}" if m.cost else ""
        lines.append(f"- **{m.date}**{km}: {m.description}{cost}")

    return "\n".join(lines)