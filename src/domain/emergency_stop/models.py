"""Pure models for the manual emergency stop (BL-44/specs/031).

No Agno, no I/O. ``reason`` is operator-authored free text: it may appear in
logs and in the admin API response, but must never reach telemetry
attributes (same discipline already applied to ``CostGovernanceError``).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class EmergencyStopState:
    """Current state of the manual emergency stop."""

    active: bool
    reason: str | None = None
    activated_by: str | None = None
    activated_at: datetime | None = None


class EmergencyStopActiveError(RuntimeError):
    """Raised to fail closed when the operator has manually stopped inference."""

    def __init__(self, reason: str | None):
        super().__init__(f"Emergency stop is active: {reason or 'no reason recorded'}")
        self.reason = reason


__all__ = ["EmergencyStopActiveError", "EmergencyStopState"]
