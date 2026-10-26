"""Stability report for the PyRIT candidate ledger (no inference, no content).

Reuses ``scripts/report_evals`` on ``evals/runs/redteam_ledger.jsonl`` so the
lightweight baseline ledger is never mixed with red-team passes. Passes recorded
with a different provider guardrail state measure different things, so the report
filters on it::

    python -m scripts.pyrit_redteam.report_candidate --guardrail block --last 3
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import report_evals  # noqa: E402
from scripts.pyrit_redteam.run_candidate import LEDGER  # noqa: E402


def select_passes(
    runs: list[dict], guardrail: str, last: int, min_cases: int, converters: list[str] | None
) -> list[dict]:
    """Passes recorded under one guardrail state, optionally for one converter set."""
    chosen = [
        run for run in runs
        if run.get("provider_guardrail") == guardrail
        and run["cases"] >= min_cases
        and (converters is None or sorted(run.get("converter_filter", [])) == sorted(converters))
    ]
    return chosen[-last:]


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--guardrail", required=True, choices=["block", "flag", "off"])
    parser.add_argument("--last", type=int, default=3)
    parser.add_argument("--min-cases", type=int, default=10,
                        help="ignore partial passes (they distort per-case stability)")
    parser.add_argument("--converter", action="append",
                        help="only passes launched with exactly this converter filter")
    args = parser.parse_args(argv)
    if not LEDGER.exists():
        print("No red-team ledger yet.")
        return 1
    runs = select_passes(report_evals.load(LEDGER), args.guardrail, args.last, args.min_cases,
                         args.converter)
    if not runs:
        print("No passes match the filter.")
        return 1
    print(f"Guardrail del proveedor: {args.guardrail}")
    print(report_evals.render(runs))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
