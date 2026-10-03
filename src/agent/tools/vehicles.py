"""Vehicle tools — thin Agno tool adapters for VehicleService.

All WRITE operations use action proposals for governance.
"""

from uuid import UUID

from agno.run import RunContext
from pydantic import ValidationError

from src.agent.tools.sessions import closes_sessions, track_session
from src.agent.tools.untrusted_results import (
    MAX_RESULT_RECORDS,
    MAX_SUMMARY_CHARS,
    MAX_TITLE_CHARS,
    bounded_text,
    render_retrieved_records,
)
from src.agent.tools.validation import internal_error_reply, parse_optional_uuid
from src.domain.vehicles.models import Vehicle, VehicleCreate, VehicleMaintenance
from src.domain.vehicles.service import VehicleService
from src.repositories.actions import ActionProposalsRepository
from src.repositories.database import get_session
from src.repositories.maintenance import MaintenanceRepository
from src.repositories.vehicles import VehiclesRepository
from src.security.user_context import UserContext


async def _get_vehicle_service() -> VehicleService:
    session = track_session(await get_session())
    return VehicleService(VehiclesRepository(session), MaintenanceRepository(session))


async def _get_actions_repo() -> ActionProposalsRepository:
    session = track_session(await get_session())
    return ActionProposalsRepository(session)


def _vehicle_record(v: Vehicle) -> dict[str, object]:
    """Bound and label a vehicle's free-text fields (make/model/nickname/plate)."""
    display_name, display_name_truncated = bounded_text(v.display_name, MAX_TITLE_CHARS)
    make, make_truncated = bounded_text(v.make, MAX_TITLE_CHARS)
    model, model_truncated = bounded_text(v.model, MAX_TITLE_CHARS)
    record: dict[str, object] = {
        "source": "vehicle",
        "id": str(v.id),
        "display_name": display_name,
        "display_name_truncated": display_name_truncated,
        "make": make,
        "make_truncated": make_truncated,
        "model": model,
        "model_truncated": model_truncated,
        "year": v.year,
    }
    if v.registration:
        registration, registration_truncated = bounded_text(v.registration, MAX_TITLE_CHARS)
        record["registration"] = registration
        record["registration_truncated"] = registration_truncated
    return record


@closes_sessions
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
        return render_retrieved_records("find_vehicle", [_vehicle_record(result.vehicle)], 1)

    if result.status == "ambiguous":
        candidates = result.candidates[:MAX_RESULT_RECORDS]
        records = [_vehicle_record(v) for v in candidates]
        return render_retrieved_records("find_vehicle", records, len(result.candidates))

    return result.message


def _maintenance_record(m: VehicleMaintenance) -> dict[str, object]:
    """Bound and label a maintenance entry's free-text fields (invoice-origin)."""
    description, description_truncated = bounded_text(m.description, MAX_SUMMARY_CHARS)
    record: dict[str, object] = {
        "source": "vehicle_maintenance",
        "id": str(m.id),
        "date": m.date.isoformat(),
        "mileage_km": m.mileage_km,
        "description": description,
        "description_truncated": description_truncated,
    }
    if m.workshop:
        workshop, workshop_truncated = bounded_text(m.workshop, MAX_TITLE_CHARS)
        record["workshop"] = workshop
        record["workshop_truncated"] = workshop_truncated
    if m.cost:
        cost, cost_truncated = bounded_text(m.cost, MAX_TITLE_CHARS)
        record["cost"] = cost
        record["cost_truncated"] = cost_truncated
    if m.work_performed:
        work_performed, work_performed_truncated = bounded_text(
            ", ".join(m.work_performed), MAX_SUMMARY_CHARS
        )
        record["work_performed"] = work_performed
        record["work_performed_truncated"] = work_performed_truncated
    return record


@closes_sessions
async def get_vehicle_summary(run_context: RunContext, vehicle_id: str) -> str:
    """Get a complete summary of a vehicle including last maintenance.

    Use when the user asks about a specific vehicle's status.
    Use find_vehicle first to get the vehicle_id.

    Args:
        run_context: Injected by Agno.
        vehicle_id: UUID from find_vehicle results.
    """
    user_ctx = UserContext.from_run_context(run_context)

    try:
        vid = UUID(vehicle_id)
    except ValueError:
        return f"ID de vehículo no válido: {vehicle_id}"

    service = await _get_vehicle_service()
    summary = await service.get_summary(user_ctx, vid)
    if not summary:
        return f"Vehículo no encontrado: {vehicle_id}"

    record = _vehicle_record(summary.vehicle)
    record["total_maintenance_count"] = summary.total_maintenance_count
    record["last_maintenance"] = (
        _maintenance_record(summary.last_maintenance) if summary.last_maintenance else None
    )
    return render_retrieved_records("get_vehicle_summary", [record], 1)


@closes_sessions
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

    src_doc = parse_optional_uuid(source_document_id, "documento")
    if isinstance(src_doc, str):
        return src_doc

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


@closes_sessions
async def execute_vehicle(run_context: RunContext, proposal_id: str) -> str:
    """Execute a confirmed vehicle registration proposal.

    Only call after user explicitly confirmed (e.g. 'Sí' after a proposal).

    Args:
        run_context: Injected by Agno.
        proposal_id: The proposal ID from propose_vehicle.
    """
    user_ctx = UserContext.from_run_context(run_context)
    actions_repo = await _get_actions_repo()
    proposal = await actions_repo.confirm_or_use_confirmed(user_ctx.user_id, proposal_id)
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
        # Domain rule (e.g. duplicate registration): the service builds a
        # user-facing Spanish message from canonical data, never infra detail.
        # The proposal stays confirmed, not executed.
        return f"❌ No se pudo registrar el vehículo: {str(e)[:200]}"
    except Exception as e:
        return internal_error_reply("execute_vehicle", e)


@closes_sessions
async def get_vehicle_maintenance_history(run_context: RunContext, vehicle_id: str) -> str:
    """Get the full maintenance history for a vehicle.

    Args:
        run_context: Injected by Agno.
        vehicle_id: UUID from find_vehicle results.
    """
    user_ctx = UserContext.from_run_context(run_context)

    try:
        vid = UUID(vehicle_id)
    except ValueError:
        return f"ID de vehículo no válido: {vehicle_id}"

    service = await _get_vehicle_service()
    records = await service.get_maintenance_history(user_ctx, vid)
    if not records:
        return "No hay registros de mantenimiento para este vehículo."

    bounded_records = [_maintenance_record(m) for m in records[:MAX_RESULT_RECORDS]]
    return render_retrieved_records(
        "get_vehicle_maintenance_history", bounded_records, len(records)
    )
