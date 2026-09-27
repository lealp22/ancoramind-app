"""Structural checks for the versioned Spec 016 alert definitions."""

from __future__ import annotations

import json
from pathlib import Path

ALERTS_PATH = (
    Path(__file__).resolve().parents[2]
    / "observability"
    / "alerts"
    / "ancoramind-health-alerts.json"
)


def test_health_alerts_reference_existing_metrics_and_bounded_metric_labels() -> None:
    payload = json.loads(ALERTS_PATH.read_text(encoding="utf-8"))
    rules = payload["groups"][0]["rules"]
    expressions = {rule["alert"]: rule["expr"] for rule in rules}

    assert set(expressions) == {
        "AncoraMindGatewayCircuitOpen",
        "AncoraMindCostHardStop",
        "AncoraMindTelegramDeliveryErrors",
        "AncoraMindReminderWorkerHeartbeatMissing",
        "AncoraMindNoAcceptedInteractions",
    }
    assert (
        'ancora_gateway_circuit_state{ancora_circuit_state="open"}'
        in expressions["AncoraMindGatewayCircuitOpen"]
    )
    assert "ancora_cost_governance_hard_stop_total" in expressions["AncoraMindCostHardStop"]
    assert (
        'ancora_telegram_deliveries_total{ancora_delivery_status="error"}'
        in expressions["AncoraMindTelegramDeliveryErrors"]
    )
    assert (
        'ancora_health_component{ancora_health_component="reminder_worker"}'
        in expressions["AncoraMindReminderWorkerHeartbeatMissing"]
    )
    heartbeat_metric = 'ancora_health_heartbeat_total{ancora_health_component="reminder_worker"}'
    assert heartbeat_metric in expressions["AncoraMindReminderWorkerHeartbeatMissing"]
    assert (
        'ancora_telegram_admissions_total{ancora_admission_status="accepted"}'
        in expressions["AncoraMindNoAcceptedInteractions"]
    )


def test_health_alerts_link_to_the_documented_runbook_and_have_bounded_rule_labels() -> None:
    payload = json.loads(ALERTS_PATH.read_text(encoding="utf-8"))
    for rule in payload["groups"][0]["rules"]:
        assert rule["labels"].keys() == {"severity", "component"}
        assert rule["labels"]["severity"] in {"warning", "critical"}
        assert rule["annotations"]["runbook"].startswith("docs/runbooks-013.md#")
