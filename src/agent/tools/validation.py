"""Shared input validation and safe error replies for tools (specs/023 T3).

Tool return values reach the LLM and the user. Exception text can carry SQL,
driver or provider details, so it is never echoed: the reply is a fixed
Spanish message and only the exception *class* is logged (the structured log
formatter drops message text anyway — see ``MetadataOnlyJsonFormatter``).
"""

from __future__ import annotations

import logging
from uuid import UUID

logger = logging.getLogger(__name__)

INVALID_PROPOSAL_DATA = "❌ Los datos de la propuesta no son válidos. Crea una propuesta nueva."
INTERNAL_ERROR = "❌ Error interno al procesar la operación. Inténtalo de nuevo más tarde."
INVALID_RECURRENCE = (
    "Regla de recurrencia no válida. Usa frecuencia 'daily', 'weekly', 'monthly' o 'yearly'; "
    "intervalo entero entre 1 y 365; y, si indicas recurrence_until, una fecha-hora ISO 8601 "
    "con zona explícita (offset o Z), no una fecha sola ni una hora sin zona. "
    "El límite es inclusivo. No se ha creado ninguna propuesta."
)


def parse_uuid(value: str | None, label: str) -> UUID | str:
    """Parse a UUID from tool input; return a user-facing message if invalid.

    The rejected value is not echoed back: it is LLM-supplied and unbounded.
    """
    try:
        return UUID(str(value))
    except (ValueError, TypeError, AttributeError):
        return f"ID no válido ({label}). Usa el identificador exacto devuelto por la tool."


def parse_optional_uuid(value: str | None, label: str) -> UUID | str | None:
    """Like ``parse_uuid`` but ``None``/empty means "not provided"."""
    if value is None or not str(value).strip():
        return None
    return parse_uuid(value, label)


def invalid_proposal_reply(tool: str, exc: BaseException) -> str:
    """Log a malformed stored proposal and return a fixed, content-free reply."""
    logger.warning(
        "Tool rejected proposal payload (tool=%s, error_class=%s)", tool, type(exc).__name__
    )
    return INVALID_PROPOSAL_DATA


def internal_error_reply(tool: str, exc: BaseException) -> str:
    """Log an unexpected tool failure and return a fixed, content-free reply."""
    logger.error(
        "Tool failed unexpectedly (tool=%s, error_class=%s)", tool, type(exc).__name__
    )
    return INTERNAL_ERROR
