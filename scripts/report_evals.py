"""Informe agregado de evals/runs/ledger.jsonl: estabilidad por caso entre pasadas.

Uso:
    python scripts/report_evals.py                # últimas N pasadas completas
    python scripts/report_evals.py --last 5
    python scripts/report_evals.py --sha d0d91dc  # sólo pasadas de un SHA

Sólo lee el ledger (sin contenido). No hace inferencia.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

LEDGER = Path(__file__).resolve().parent.parent / "evals" / "runs" / "ledger.jsonl"
STATUSES = ("pass", "review", "fail", "error", "unevaluated")


def load(path: Path = LEDGER) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def select(runs: list[dict], last: int, sha: str | None, min_cases: int) -> list[dict]:
    """Sólo pasadas casi completas: las parciales distorsionan la estabilidad por caso."""
    chosen = [r for r in runs if r["cases"] >= min_cases and (sha is None or r["git_sha"] == sha)]
    return chosen[-last:]


def per_case(runs: list[dict]) -> dict[str, list[str]]:
    table: dict[str, list[str]] = defaultdict(list)
    for run in runs:
        for row in run["rows"]:
            table[row["case_id"]].append(row["status"])
    return table


def cost_label(run: dict) -> str:
    """Coste Agent + juez: el informado por OpenRouter; «~» marca una estimación."""
    agent = run.get("agent_cost_usd")
    agent_est = run.get("agent_cost_est_usd")
    judge = run.get("judge_cost_usd")
    judge_est = run.get("judge_cost_est_usd")
    if "judge_cost_est_usd" not in run:
        # Ledger anterior: judge_cost_usd era siempre un recálculo con tarifa fija.
        judge, judge_est = None, judge

    def part(real: float | None, est: float | None) -> str:
        if real is not None:
            return str(real)
        return f"~{est}" if est is not None else "?"

    return f"{part(agent, agent_est)}+{part(judge, judge_est)} USD"


def render(runs: list[dict]) -> str:
    table = per_case(runs)
    lines = [f"Pasadas: {len(runs)}  ({runs[0]['ts']} → {runs[-1]['ts']})", ""]
    totals = [
        f"  pasada {i}: {r['passed']}/{r['cases']} pass  sha={r['git_sha']}  "
        f"tokens_in={r['agent_input_tokens']}  coste={cost_label(r)}"
        for i, r in enumerate(runs, 1)
    ]
    lines += totals + [""]
    stable = {c: s for c, s in table.items() if len(set(s)) == 1}
    noisy = {c: s for c, s in table.items() if len(set(s)) > 1}
    always_pass = [c for c, s in stable.items() if s[0] == "pass"]
    lines.append(f"Estables en pass: {len(always_pass)}/{len(table)}")
    lines.append(f"Estables sin pass: {len(stable) - len(always_pass)}")
    lines.append(f"Inestables (cambian de estado entre pasadas): {len(noisy)}")
    for case_id, states in sorted(stable.items()):
        if states[0] != "pass":
            lines.append(f"  SIEMPRE {states[0]:11} {case_id}")
    for case_id, states in sorted(noisy.items()):
        counts = Counter(states)
        detail = ", ".join(f"{k}={counts[k]}" for k in STATUSES if counts[k])
        lines.append(f"  RUIDO   {detail:32} {case_id}")
    return "\n".join(lines)


def main() -> int:
    # Con la salida redirigida en Windows el códec es cp1252 y la flecha de la cabecera
    # no cabe: forzar UTF-8 evita el UnicodeEncodeError.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--last", type=int, default=5)
    parser.add_argument("--sha")
    parser.add_argument("--min-cases", type=int, default=50,
                        help="ignora pasadas con menos casos (parciales)")
    args = parser.parse_args()
    runs = select(load(), args.last, args.sha, args.min_cases)
    if not runs:
        print("Sin pasadas que cumplan el filtro.")
        return 1
    print(render(runs))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
