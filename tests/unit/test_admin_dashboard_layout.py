"""Dashboard sections and safe health rendering without a running app or DB."""

from html.parser import HTMLParser
from pathlib import Path

import pytest

HTML = Path(__file__).parents[2] / "src" / "agent" / "admin_dashboard_static" / "dashboard.html"


class DashboardStructure(HTMLParser):
    def __init__(self, source: str) -> None:
        super().__init__()
        self.tabs: list[dict[str, str | None]] = []
        self.panels: dict[str, dict[str, str | None]] = {}
        self.owners: dict[str, str | None] = {}
        self.current_panel: str | None = None
        self.feed(source)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if values.get("role") == "tab":
            self.tabs.append(values)
        element_id = values.get("id")
        if tag == "section" and values.get("role") == "tabpanel":
            assert element_id is not None
            self.current_panel = element_id
            self.panels[element_id] = values
        if element_id:
            assert element_id not in self.owners, f"Duplicate id: {element_id}"
            self.owners[element_id] = self.current_panel

    def handle_endtag(self, tag: str) -> None:
        if tag == "section":
            self.current_panel = None


def test_dashboard_tabs_have_linked_panels_and_summary_selected_by_default() -> None:
    layout = DashboardStructure(HTML.read_text(encoding="utf-8"))
    assert [tab["id"] for tab in layout.tabs] == ["tab-summary", "tab-proposals", "tab-admin"]
    assert len(layout.panels) == 3
    for index, tab in enumerate(layout.tabs):
        panel = layout.panels[tab["aria-controls"]]
        assert panel["aria-labelledby"] == tab["id"]
        assert tab["aria-selected"] == ("true" if index == 0 else "false")
        assert tab["tabindex"] == ("0" if index == 0 else "-1")
        assert ("hidden" in panel) == (index != 0)


@pytest.mark.parametrize(
    "panel,element_ids",
    [
        (
            "panel-summary",
            (
                "health-summary",
                "finops-panel",
                "fo-days",
                "fo-error",
                "fo-kpis",
                "fo-budget",
                "fo-daily",
                "fo-users",
                "fo-routes",
                "fo-sources",
                "fo-sources-chart",
                "fo-quality-kpis",
                "fo-proposal-rates",
                "fo-statuses",
                "fo-statuses-chart",
                "fo-excluded",
            ),
        ),
        ("panel-proposals", ("fo-proposals", "proposals-days", "proposals-error")),
        (
            "panel-admin",
            (
                "inv-max-uses",
                "rc-status",
                "health-table",
                "health-raw",
                "links-table",
            ),
        ),
    ],
)
def test_dashboard_groups_existing_controls_in_the_requested_tab(
    panel: str, element_ids: tuple[str, ...]
) -> None:
    layout = DashboardStructure(HTML.read_text(encoding="utf-8"))
    for element_id in element_ids:
        assert layout.owners[element_id] == panel


def test_health_summary_and_details_share_one_request_and_safe_dom_rendering() -> None:
    source = HTML.read_text(encoding="utf-8")
    block = source.split("async function loadHealth() {", 1)[1].split(
        "async function loadLinks()", 1
    )[0]
    assert source.count('fetch("/health/readiness")') == 1
    assert 'document.getElementById("health-summary")' in block
    assert 'document.querySelector("#health-table tbody")' in block
    assert "summary.textContent = components.map" in block
    assert "if (!res.ok)" in block
    assert '"❔ Salud no disponible"' in block
    for state in ("healthy", "degraded", "disabled", "unknown"):
        assert f"{state}:" in block
    for sink in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval("):
        assert sink not in block


def test_dashboard_supports_keyboard_navigation_and_shared_finops_window() -> None:
    source = HTML.read_text(encoding="utf-8")
    navigation = source.split("function selectTab(", 1)[1].split("function login()", 1)[0]
    for key in ("ArrowRight", "ArrowLeft", "Home", "End"):
        assert f'event.key === "{key}"' in navigation
    assert 'tab.setAttribute("aria-selected", String(active))' in navigation
    assert ".hidden = !active" in navigation
    assert ".focus()" in navigation
    assert "fetch(" not in navigation
    assert source.count('onchange="setFinopsWindow(this.value)"') == 2
    window = source.split("function setFinopsWindow(days)", 1)[1].split(
        "async function loadFinops()", 1
    )[0]
    assert 'document.getElementById("fo-days").value = days' in window
    assert 'document.getElementById("proposals-days").value = days' in window
    assert "loadFinops();" in window
