"""Reader boundary consumed on the inference hot path (BL-44/specs/031).

Deliberately synchronous and zero-I/O: both call sites that consume this
(``GovernedModelMixin.ainvoke`` for every physical model call, and
``GovernedInteractionRunner.prepare_execution_context`` once per run) must
never add a database round trip to the inference critical path. A future
durable, Postgres-backed implementation stays behind this same Protocol —
not defined in this increment (spec.md §8).
"""

from __future__ import annotations

from typing import Protocol

from src.domain.emergency_stop.models import EmergencyStopState


class EmergencyStopReader(Protocol):
    """Cheap, synchronous read of the current emergency-stop state."""

    def current(self) -> EmergencyStopState: ...


__all__ = ["EmergencyStopReader"]
