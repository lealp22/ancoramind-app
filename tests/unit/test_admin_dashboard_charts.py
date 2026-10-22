"""Exercise the actual chart JavaScript offline using Node's built-in VM.

No browser or database dependencies. Node is optional in Python-only environments;
the browser check additionally verifies layout and CSS with synthetic responses.
"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

HTML = Path(__file__).parents[2] / "src" / "agent" / "admin_dashboard_static" / "dashboard.html"
NODE = shutil.which("node")

HARNESS = r"""
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const input = JSON.parse(fs.readFileSync(0, 'utf8'));
class Element {
  constructor(tag) {
    this.tag = tag; this.children = []; this.style = {}; this.attrs = {};
    this._text = ''; this.className = '';
  }
  set textContent(value) { this._text = String(value); this.children = []; }
  get textContent() { return this._text + this.children.map(c => c.textContent).join(' '); }
  appendChild(child) { this.children.push(child); return child; }
  append(...children) { this.children.push(...children); }
  replaceChildren(...children) { this.children = children; this._text = ''; }
  setAttribute(key, value) { this.attrs[key] = String(value); }
}
const nodes = {};
const document = {
  createElement: tag => new Element(tag),
  getElementById: id => nodes[id] ??= new Element('div'),
};
const context = vm.createContext({document, assert, nodes});
const start = input.source.indexOf('// ---- FinOps y calidad');
const end = input.source.indexOf('function renderFinops(');
vm.runInContext(input.source.slice(start, end), context);
vm.runInContext(input.test, context);
"""

CASES = {
    "daily_90_days_fixed_height_and_exact_values": r"""
const rows = Array.from({length:90}, (_,i) => ({
  day:new Date(Date.UTC(2026,0,i+1)).toISOString().slice(0,10), cost_usd:i/100
}));
renderDaily(rows.reverse());
const box = nodes['fo-daily'];
const plot = box.children[0].children[1];
assert.equal(plot.children.length,90);
assert.match(plot.children[0].attrs['aria-label'],/^2026-01-01: \$0.0000$/);
assert.equal(plot.children[89].style.height,'100%');
assert.ok(parseFloat(plot.children[0].style.left) < parseFloat(plot.children[89].style.left));
assert.ok(box.children[1].children.length <= 3);
const table = box.children[3].children[1];
assert.equal(table.children[1].children.length,90);
assert.equal(table.children[1].children[89].children[1].textContent,'$0.8900');
""",
    "daily_missing_dates_are_gaps_and_empty_clears_chart": r"""
renderDaily([{day:'2026-10-01',cost_usd:1},{day:'2026-10-03',cost_usd:0}]);
const columns = nodes['fo-daily'].children[0].children[1].children;
assert.equal(columns.length,2);
assert.ok(parseFloat(columns[1].style.left) > 66);
assert.equal(columns[1].style.height,'0%');
renderDaily([]);
assert.equal(nodes['fo-daily'].children.length,1);
assert.match(nodes['fo-daily'].textContent,/Sin datos/);
""",
    "daily_zero_does_not_divide_by_zero": r"""
renderDaily([{day:'2026-10-01',cost_usd:0}]);
const column = nodes['fo-daily'].children[0].children[1].children[0];
assert.equal(column.style.height,'0%');
assert.match(column.className,/zero/);
assert.equal(column.title,'2026-10-01: $0.0000');
""",
    "donut_uses_cost_not_calls_and_shows_percentages": r"""
renderDonut('cost','Coste',[
  {label:'actual',value:3,calls:1},{label:'estimated',value:1,calls:100}
],usd,'Sin gasto');
const [ring,legend] = nodes.cost.children[0].children;
assert.match(ring.style.background,/0% 75%/);
assert.match(legend.textContent,/actual: \$3.0000 · 75.0 %/);
assert.match(legend.textContent,/estimated: \$1.0000 · 25.0 %/);
assert.match(ring.attrs['aria-label'],/total \$4.0000/);
assert.equal(ring.children[0].children[0].textContent,'$4.0000');
""",
    "donut_single_zero_empty_and_untrusted_labels": r"""
renderDonut('states','Estados',[{label:'<img src=x>',value:4}],String,'Sin datos');
const [ring,legend] = nodes.states.children[0].children;
assert.match(ring.style.background,/0% 100%/);
assert.match(legend.textContent,/<img src=x>: 4 · 100.0 %/);
assert.equal(legend.children[0].children[1].tag,'span');
renderDonut('states','Estados',[{label:'completed',value:0}],String,'Sin datos');
assert.equal(nodes.states.children.length,1);
assert.equal(nodes.states.textContent,'Sin datos');
renderDonut('states','Estados',[],String,'Sin datos');
assert.equal(nodes.states.textContent,'Sin datos');
""",
    "proposal_rates_share_denominator_without_thresholds": r"""
renderProposalRates({resolved:10,executed:7,discarded:2,expired:1,
  executed_rate:0.7,discarded_rate:0.2,expired_rate:0.1});
const box = nodes['fo-proposal-rates'];
const bars = box.children.filter(c => c.attrs.role === 'meter');
assert.equal(bars.length,3);
assert.equal(bars.map(c => c.children[0].style.width).join(','),'70%,20%,10%');
assert.equal(bars.map(c => c.className).join(','),'bar,bar,bar');
for (const bar of bars) {
  assert.equal(bar.attrs['aria-valuemax'],'100');
  assert.equal(bar.attrs['aria-valuemin'],'0');
}
assert.match(box.textContent,/70.0 % \(7 \/ 10\)/);
assert.match(box.textContent,/10.0 % \(1 \/ 10\)/);
""",
    "proposal_zero_is_not_missing_and_empty_clears_old_values": r"""
renderProposalRates({resolved:1,executed:1,discarded:0,expired:0,
  executed_rate:1,discarded_rate:0,expired_rate:0});
let bars = nodes['fo-proposal-rates'].children.filter(c => c.attrs.role === 'meter');
assert.equal(bars[1].attrs['aria-valuenow'],'0');
assert.equal(bars[1].children[0].style.width,'0%');
renderProposalRates({resolved:0,executed_rate:null,discarded_rate:null,expired_rate:null});
assert.equal(nodes['fo-proposal-rates'].children.length,1);
assert.match(nodes['fo-proposal-rates'].textContent,/Sin propuestas resueltas/);
""",
}


@pytest.mark.skipif(NODE is None, reason="Node.js optional for offline JavaScript checks")
@pytest.mark.parametrize("case", CASES)
def test_chart_rendering(case: str) -> None:
    assert NODE is not None
    result = subprocess.run(
        [NODE, "-e", HARNESS],
        input=json.dumps({"source": HTML.read_text(encoding="utf-8"), "test": CASES[case]}),
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=15,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_charts_are_wired_to_the_existing_aggregates() -> None:
    source = HTML.read_text(encoding="utf-8")
    assert "renderDaily(data.daily)" in source
    assert 'renderDonut("fo-sources-chart"' in source
    assert "value: s.cost_usd" in source
    assert 'renderDonut("fo-statuses-chart"' in source
    assert "value: s.count" in source
    rates = source.split("function renderProposalRates(", 1)[1].split("function renderFinops(", 1)[
        0
    ]
    for forbidden in ("warn", "bad", "threshold", ">= 90", "> 10"):
        assert forbidden not in rates
