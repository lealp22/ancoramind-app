"""Regression checks for the demo dashboard's confirmed Prometheus names."""

import json
from pathlib import Path


def test_health_dashboard_uses_confirmed_counter_names() -> None:
    path = (
        Path(__file__).resolve().parents[2]
        / "observability"
        / "dashboards"
        / "ancoramind-health.json"
    )
    dashboard = json.loads(path.read_text(encoding="utf-8"))
    panels = {panel["title"]: panel for panel in dashboard["panels"]}
    heartbeat = panels["Heartbeats recientes"]["targets"][0]["expr"]
    admission = panels["Admission y deliveries"]["targets"][0]["expr"]
    assert "ancora_health_heartbeat_total[" in heartbeat
    assert "ancora_telegram_admissions_total[" in admission
    assert dashboard["uid"] == "ancoramind-health"
    assert all("alert" not in panel for panel in dashboard["panels"])
