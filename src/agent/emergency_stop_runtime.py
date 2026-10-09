"""Process-wide accessor for the manual emergency-stop manager (BL-44/specs/031).

Every call site that builds its own ``AgnoLLMAccess`` outside the main
conversational run's DI chain (``src/main.py``/``src/agent/lifecycle.py``)
must still share the *same* ``EmergencyStopManager`` instance for the
operator's manual stop to actually take effect there. Same pattern as
``get_telemetry()``/``get_session()``: one module-level singleton, lazily
created on first access.
"""

from __future__ import annotations

from src.domain.emergency_stop.service import EmergencyStopManager

_manager = EmergencyStopManager()


def get_emergency_stop_manager() -> EmergencyStopManager:
    """Return the single process-wide emergency-stop manager."""
    return _manager


__all__ = ["get_emergency_stop_manager"]
