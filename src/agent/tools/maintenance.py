"""Register vehicle maintenance — WRITE tools with action proposal pattern.

These tools require confirmation per governance policy.
"""

from datetime import date
from decimal import Decimal, InvalidOperation
from uuid import UUID

from agno.run import RunContext

from src.agent.tools.sessions import closes_sessions, track_session
from src.agent.tools.validation import (
    internal_error_reply,
    invalid_proposal_reply,
    parse_optional_uuid,
)
from src.domain.actions.models import ProposalStatus
from src.domain.vehicles.money import format_money, parse_legacy_money
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


@closes_sessions
async def propose_vehicle_maintenance(
    run_context: RunContext,
    vehicle_id: str,
    date_str: str,
    description: str,
    mileage_km: int | None = None,
    workshop: str | None = None,
    cost_amount: str | None = None,
    cost_currency: str | None = None,
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
        cost_amount: Optional decimal amount (e.g. '286.40'). Requires cost_currency.
        cost_currency: Optional ISO 4217 code (e.g. 'EUR'). Requires cost_amount.
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

    amount: Decimal | None = None
    currency: str | None = None
    if (cost_amount is None) != (cost_currency is None):
        return "Importe y divisa deben indicarse juntos (por ejemplo, 286.40 y EUR)."
    if cost_amount is not None and cost_currency is not None:
        try:
            amount = Decimal(cost_amount).quantize(Decimal("0.01"))
        except (InvalidOperation, ValueError):
            return "Importe no válido. Usa un decimal, por ejemplo 286.40."
        currency = cost_currency.strip().upper()
        if amount < 0 or len(currency) != 3 or not currency.isalpha():
            return (
                "Importe o divisa no válidos. Usa una divisa ISO de tres letras, "
                "por ejemplo EUR."
            )

    work_items = [w.strip() for w in (work_performed or "").split(",") if w.strip()]

    src_doc = parse_optional_uuid(source_document_id, "documento")
    if isinstance(src_doc, str):
        return src_doc

    # Verify vehicle belongs to user
    service = await _get_vehicle_service()
    target = await service.get_vehicle(user_ctx, vid)
    if not target:
        return f"Vehículo no encontrado: {vehicle_id}"

    # Create action proposal
    actions_repo = await _get_actions_repo()
    proposal = await actions_repo.create(
        user_id=user_ctx.user_id,
        tool_name="register_vehicle_maintenance",
        payload={
            "vehicle_id": str(vid),
            "date": date_str,
            "description": description,
            "mileage_km": mileage_km,
            "workshop": workshop,
            "cost_amount": str(amount) if amount is not None else None,
            "cost_currency": currency,
            "work_performed": work_items,
            "notes": notes,
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
    formatted_amount = format_money(amount, currency)
    if formatted_amount:
        lines.append(f"   Importe: {formatted_amount}")
    if work_items:
        lines.append(f"   Trabajos: {', '.join(work_items)}")
    lines.append("\n¿Confirmas el registro de este mantenimiento?")
    return "\n".join(lines)


@closes_sessions
async def execute_vehicle_maintenance(run_context: RunContext, proposal_id: str) -> str:
    """Execute a confirmed vehicle maintenance proposal.

    Only call after user explicitly confirmed (e.g. 'Sí' after a proposal).

    Args:
        run_context: Injected by Agno.
        proposal_id: The proposal ID from propose_vehicle_maintenance.

    """
    user_ctx = UserContext.from_run_context(run_context)
    session = track_session(await get_session())
    actions_repo = ActionProposalsRepository(session)
    proposal = await actions_repo.confirm_or_use_confirmed(user_ctx.user_id, proposal_id)
    if not proposal:
        return f"No se encontró la propuesta `{proposal_id}` o ya no está pendiente."

    payload = proposal["payload"]
    service = VehicleService(VehiclesRepository(session), MaintenanceRepository(session))
    try:
        if not await actions_repo.begin_execution(UUID(proposal_id), user_id=user_ctx.user_id):
            return f"No se encontró la propuesta `{proposal_id}` o ya no está pendiente."
        if "cost_amount" in payload:
            amount = Decimal(payload["cost_amount"]) if payload.get("cost_amount") else None
            currency = payload.get("cost_currency")
        else:
            legacy_money = parse_legacy_money(payload.get("cost"))
            amount, currency = legacy_money if legacy_money else (None, None)
        record = await service.register_maintenance(
            user_context=user_ctx,
            vehicle_id=UUID(payload["vehicle_id"]),
            maintenance_date=date.fromisoformat(payload["date"]),
            description=payload["description"],
            mileage_km=payload.get("mileage_km"),
            workshop=payload.get("workshop"),
            cost_amount=amount,
            cost_currency=currency,
            work_performed=payload.get("work_performed", []),
            notes=payload.get("notes"),
            source_document_id=UUID(payload["source_document_id"])
            if payload.get("source_document_id")
            else None,
            source_action_id=UUID(proposal_id),
            commit=False,
        )
        await actions_repo.complete_execution(
            UUID(proposal_id), user_id=user_ctx.user_id, status=ProposalStatus.EXECUTED
        )
        await session.commit()

        lines = [
            "✅ **Mantenimiento registrado**",
            f"   Fecha: {record.date} — {record.description}",
        ]
        formatted_amount = format_money(record.cost_amount, record.cost_currency)
        if formatted_amount:
            lines.append(f"   Importe: {formatted_amount}")
        lines.append(f"   ID: `{record.id}`")
        if payload.get("source_document_id"):
            lines.append(f"   Documento origen: `{payload['source_document_id']}`")
        return "\n".join(lines)
    except (KeyError, TypeError, ValueError, InvalidOperation) as e:
        await session.rollback()
        await _mark_execution_failed(actions_repo, session, proposal_id, user_ctx.user_id,
                                     "invalid_maintenance_payload")
        return invalid_proposal_reply("execute_vehicle_maintenance", e)
    except Exception as e:
        await session.rollback()
        await _mark_execution_failed(actions_repo, session, proposal_id, user_ctx.user_id,
                                     "maintenance_execution_failed")
        return internal_error_reply("execute_vehicle_maintenance", e)


async def _mark_execution_failed(
    actions_repo: ActionProposalsRepository,
    session: object,
    proposal_id: str,
    user_id: str,
    reason: str,
) -> None:
    """Terminally close a rolled-back maintenance execution when it is safe to do so."""
    if await actions_repo.begin_execution(UUID(proposal_id), user_id=user_id):
        await actions_repo.complete_execution(
            UUID(proposal_id),
            user_id=user_id,
            status=ProposalStatus.FAILED_DEFINITIVE,
            failure_reason=reason,
        )
        await session.commit()  # type: ignore[attr-defined]
