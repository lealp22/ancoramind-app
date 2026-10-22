"""Regression checks for the demo dashboard's confirmed Prometheus names."""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DASHBOARD = ROOT / "observability" / "dashboards" / "ancoramind-health.json"
TOOL_HOOK = ROOT / "src" / "agent" / "tool_budget_hooks.py"


def _dashboard() -> dict:
    return json.loads(DASHBOARD.read_text(encoding="utf-8"))


def test_health_dashboard_uses_confirmed_counter_names() -> None:
    dashboard = _dashboard()
    panels = {panel["title"]: panel for panel in dashboard["panels"]}
    heartbeat = panels["Heartbeats recientes"]["targets"][0]["expr"]
    admission = panels["Admission y deliveries"]["targets"][0]["expr"]
    assert "ancora_health_heartbeat_total[" in heartbeat
    assert "ancora_telegram_admissions_total[" in admission
    assert dashboard["uid"] == "ancoramind-health"
    assert all("alert" not in panel for panel in dashboard["panels"])


def test_tool_panels_match_the_metrics_the_hook_emits() -> None:
    """Dashboard series must follow the OTel names emitted by the tool hook.

    The Prometheus names are derived (``.`` -> ``_``, counters get ``_total``,
    millisecond histograms get ``_milliseconds_bucket``), the same convention the
    already-imported panels rely on. This guards a rename in the hook; it does not
    prove the series exist in Grafana Cloud (confirm in Explore before relying on them).
    """
    hook = TOOL_HOOK.read_text(encoding="utf-8")
    assert '"ancora.tool.calls"' in hook
    assert '"ancora.tool.call.duration"' in hook
    assert '"ancora.tool.name"' in hook
    assert '"ancora.tool.outcome"' in hook

    panels = {panel["title"]: panel for panel in _dashboard()["panels"]}
    calls = panels["Tools invocadas"]["targets"][0]["expr"]
    latency = panels["Latencia p95 por tool"]["targets"][0]["expr"]

    assert "ancora_tool_calls_total[" in calls
    assert "ancora_tool_name" in calls and "ancora_tool_outcome" in calls
    assert "ancora_tool_call_duration_milliseconds_bucket[" in latency
    assert "ancora_tool_name" in latency


def test_cost_panel_uses_the_estimated_cost_series_that_has_samples() -> None:
    """Grafana (2026-10-22) has samples for the estimated cost, not for actual cost/tokens.

    ``ancora.llm.actual_cost_usd`` and ``ancora.llm.total_tokens`` are emitted only when
    the provider returns usage, which it does not today. The panel must not depend on
    them, and must not present an estimate as billing.
    """
    panels = {panel["title"]: panel for panel in _dashboard()["panels"]}
    panel = panels["Coste estimado LLM (USD)"]
    exprs = " ".join(target["expr"] for target in panel["targets"])

    assert "ancora_llm_estimated_cost_usd_total[" in exprs
    assert "actual_cost" not in exprs and "total_tokens" not in exprs
    assert "estimado" in panel["description"].lower()


def test_dashboard_panels_are_unique_and_do_not_overlap() -> None:
    panels = _dashboard()["panels"]
    titles = [panel["title"] for panel in panels]
    assert len(titles) == len(set(titles))

    occupied: set[tuple[int, int]] = set()
    for panel in panels:
        pos = panel["gridPos"]
        assert pos["x"] + pos["w"] <= 24
        cells = {
            (x, y)
            for x in range(pos["x"], pos["x"] + pos["w"])
            for y in range(pos["y"], pos["y"] + pos["h"])
        }
        assert not cells & occupied, f"{panel['title']} overlaps another panel"
        occupied |= cells


def test_dashboard_queries_carry_no_content_labels() -> None:
    """Metadata-only: no query may group by anything that could hold user content."""
    forbidden = re.compile(r"(query|prompt|message|content|argument|result|text)", re.IGNORECASE)
    for panel in _dashboard()["panels"]:
        for target in panel.get("targets", []):
            for label in re.findall(r"by \(([^)]*)\)", target["expr"]):
                assert not forbidden.search(label), (panel["title"], label)
