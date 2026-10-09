"""Unit tests for the in-memory emergency-stop manager (BL-44/specs/031)."""

from __future__ import annotations

import pytest

from src.domain.emergency_stop.service import EmergencyStopManager


def test_bootstraps_inactive() -> None:
    manager = EmergencyStopManager()

    state = manager.current()

    assert state.active is False
    assert state.reason is None
    assert state.activated_by is None
    assert state.activated_at is None


def test_activate_updates_current_state() -> None:
    manager = EmergencyStopManager()

    state = manager.activate(actor="jesus", reason="cost spike")

    assert state.active is True
    assert state.reason == "cost spike"
    assert state.activated_by == "jesus"
    assert state.activated_at is not None
    assert manager.current() == state


def test_deactivate_resumes_inference_and_keeps_audit_trail() -> None:
    manager = EmergencyStopManager()
    manager.activate(actor="jesus", reason="cost spike")

    state = manager.deactivate(actor="jesus", reason="resolved")

    assert state.active is False
    assert state.reason == "resolved"
    assert state.activated_by == "jesus"
    assert manager.current() == state


@pytest.mark.parametrize("method", ["activate", "deactivate"])
def test_blank_actor_is_rejected(method: str) -> None:
    manager = EmergencyStopManager()

    with pytest.raises(ValueError, match="actor"):
        getattr(manager, method)(actor="   ", reason="valid reason")


@pytest.mark.parametrize("method", ["activate", "deactivate"])
def test_blank_reason_is_rejected(method: str) -> None:
    manager = EmergencyStopManager()

    with pytest.raises(ValueError, match="reason"):
        getattr(manager, method)(actor="jesus", reason="   ")
