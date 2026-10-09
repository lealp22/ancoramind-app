"""In-memory manual emergency-stop manager (BL-44/specs/031).

Mirrors ``RuntimeConfigManager``'s cached last-known-good pattern, but holds
no database backend in this increment: the state lives only in this
process's memory, so a restart silently clears it back to inactive. This is
a known, documented limitation (spec.md §8) — a durable, Postgres-backed
implementation behind the same ``EmergencyStopReader`` is explicit future
work, not something this module's shape forecloses.
"""

from __future__ import annotations

from datetime import UTC, datetime

from src.domain.emergency_stop.models import EmergencyStopState

_INACTIVE = EmergencyStopState(active=False)


class EmergencyStopManager:
    """Own the cached emergency-stop state; activate/deactivate mutate it in place."""

    def __init__(self) -> None:
        self._state: EmergencyStopState = _INACTIVE

    def current(self) -> EmergencyStopState:
        """Return the cached state without I/O (implements ``EmergencyStopReader``)."""
        return self._state

    def activate(self, *, actor: str, reason: str) -> EmergencyStopState:
        """Stop every governed inference call until explicitly deactivated."""
        self._validate_audit_fields(actor, reason)
        self._state = EmergencyStopState(
            active=True,
            reason=reason.strip(),
            activated_by=actor.strip(),
            activated_at=datetime.now(tz=UTC),
        )
        return self._state

    def deactivate(self, *, actor: str, reason: str) -> EmergencyStopState:
        """Resume governed inference; the record keeps who/why it was lifted."""
        self._validate_audit_fields(actor, reason)
        self._state = EmergencyStopState(
            active=False,
            reason=reason.strip(),
            activated_by=actor.strip(),
            activated_at=datetime.now(tz=UTC),
        )
        return self._state

    @staticmethod
    def _validate_audit_fields(actor: str, reason: str) -> None:
        if not actor.strip():
            raise ValueError("actor must not be blank")
        if not reason.strip():
            raise ValueError("reason must not be blank")


__all__ = ["EmergencyStopManager"]
