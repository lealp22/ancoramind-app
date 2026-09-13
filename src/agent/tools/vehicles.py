"""Vehicle tools — thin Agno tool adapters for VehicleService.

All WRITE operations use action proposals for governance.
"""

from uuid import UUID

from agno.run import RunContext
from pydantic import ValidationError

from src.domain.vehicles.models import VehicleCreate
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
        lines = [
            f"🚗 **{v.display_name}**",
            f"   ID: `{v.id}`",
            f"   Marca: {v.make} | Modelo: {v.model}",
        ]
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
    lines = [
        f"🚗 **{v.display_name}**",
        f"   ID: `{v.id}`",
        f"   {v.make} {v.model}"
        + (f" ({v.year})" if v.year else "")
        + (f" — {v.registration}" if v.registration else ""),
        f"   Total intervenciones: {summary.total_maintenance_count}",
    ]

    if summary.last_maintenance:
        m = summary.last_maintenance
        lines.append("\n🔧 **Último mantenimiento:**")
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


async def propose_vehicle(
    run_context: RunContext,
    make: str,
    model: str,
    year: int | None = None,
    registration: str | None = None,
    nickname: str | None = None,
    vin: str | None = None,
    source_document_id: str | None = None,
) -> str:
    """PROPOSE registering a new vehicle — requires user confirmation.

    Creates an action proposal. Does NOT write yet.
    Use when the user wants to register a new vehicle, e.g.:
    - "Registra mi coche: Ford Mondeo 2019, matrícula 1234ABC"
    - "Añade la furgoneta de la empresa"
    - "Apunta este vehículo de la factura" (tras analizar un documento)
    Requires at least make and model.

    Args:
        run_context: Injected by Agno.
        make: Brand (Ford, Toyota, etc.).
        model: Model (Mondeo, Corolla, etc.).
        year: Optional year (1900-2100).
        registration: Optional license plate.
        nickname: Optional user nickname ("mi coche", "la furgoneta").
        vin: Optional VIN/chassis number.
        source_document_id: Optional source document UUID (e.g. vehicle registration document).
    """
    user_ctx = UserContext.from_run_context(run_context)
    try:
        data = VehicleCreate(
            make=make,
            model=model,
            year=year,
            registration=registration,
            nickname=nickname,
            vin=vin,
        )
    except ValidationError as e:
        first = e.errors()[0]
        loc = first.get("loc", "?")
        msg = first.get("msg", str(e))[:150]
        return f"Datos del vehículo no válidos ({loc}: {msg})"

    src_doc = None
    if source_document_id:
        try:
            src_doc = UUID(source_document_id)
        except ValueError:
            return f"ID de documento no válido: {source_document_id}"

    actions_repo = await _get_actions_repo()
    proposal = await actions_repo.create(
        user_id=user_ctx.user_id,
        tool_name="register_vehicle",
        payload={
            "make": data.make,
            "model": data.model,
            "year": data.year,
            "registration": data.registration,
            "nickname": data.nickname,
            "vin": data.vin,
            "source_document_id": str(src_doc) if src_doc else None,
        },
        source_document_id=src_doc,
    )

    lines = [
        f"🚗 **Propuesta de nuevo vehículo** (`{proposal['id']}`)",
        f"   Marca: {data.make} | Modelo: {data.model}",
    ]
    if data.year:
        lines.append(f"   Año: {data.year}")
    if data.registration:
        lines.append(f"   Matrícula: {data.registration}")
    if data.nickname:
        lines.append(f"   Apodo: {data.nickname}")
    if data.vin:
        lines.append(f"   VIN: {data.vin}")
    lines.append("\n¿Confirmas el registro de este vehículo?")
    lines.append(
        f"\n(ID de propuesta: `{proposal['id']}` — cuando el usuario confirme, "
        "debes llamar a execute_vehicle con este ID exacto)"
    )
    return "\n".join(lines)


async def execute_vehicle(run_context: RunContext, proposal_id: str) -> str:
    """Execute a confirmed vehicle registration proposal.

    Only call after user explicitly confirmed (e.g. 'Sí' after a proposal).

    Args:
        run_context: Injected by Agno.
        proposal_id: The proposal ID from propose_vehicle.
    """
    user_ctx = UserContext.from_run_context(run_context)
    actions_repo = await _get_actions_repo()
    proposal = await actions_repo.confirm(user_ctx.user_id, proposal_id)
    if not proposal:
        return (
            f"No existe ninguna propuesta pendiente con el ID `{proposal_id}` "
            "(o ya fue ejecutada). NO la inventes: primero llama a propose_vehicle "
            "con los datos del vehículo para crear una propuesta nueva, y espera "
            "la confirmación del usuario antes de volver a ejecutar."
        )

    payload = proposal["payload"]
    try:
        data = VehicleCreate(
            make=payload["make"],
            model=payload["model"],
            year=payload.get("year"),
            registration=payload.get("registration"),
            nickname=payload.get("nickname"),
            vin=payload.get("vin"),
        )
        service = await _get_vehicle_service()
        vehicle = await service.register_vehicle(user_ctx, data)
        await actions_repo.mark_executed(user_ctx.user_id, proposal_id)

        lines = ["✅ **Vehículo registrado**", f"   {vehicle.display_name}"]
        if vehicle.registration:
            lines.append(f"   Matrícula: {vehicle.registration}")
        lines.append(f"   ID: `{vehicle.id}`")
        if payload.get("source_document_id"):
            lines.append(f"   Documento origen: `{payload['source_document_id']}`")
        return "\n".join(lines)
    except ValueError as e:
        # p.ej. matrícula duplicada — la propuesta queda confirmada, no ejecutada
        return f"❌ No se pudo registrar el vehículo: {str(e)[:200]}"
    except Exception as e:
        return f"❌ Error al registrar el vehículo: {str(e)[:200]}"


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
