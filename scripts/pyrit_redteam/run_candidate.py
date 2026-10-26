"""Run the PyRIT candidate catalog through the lightweight evaluator, unchanged.

Reuses ``scripts/run_evals_light.run_suite`` (Agent real + simulated tools, code
checks and the Span-02 judge) but feeds it cases loaded from
``evals/security_pyrit/``, which is NOT a live category. It never edits
``run_evals_light.py``, ``CATEGORIES`` or the main ledger: results go to their own
ledger so the lightweight baseline (56 cases) stays comparable.

Default is a dry run that infers nothing::

    python -m scripts.pyrit_redteam.run_candidate                  # dry run
    python -m scripts.pyrit_redteam.run_candidate --run --max-usd 0.10

It uses the repo venv (not the PyRIT one): it needs ``src/``, not PyRIT.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import run_evals_light as light  # noqa: E402
from src.agent.evals import EvalCase  # noqa: E402

CANDIDATE = ROOT / "evals" / "security_pyrit" / "candidate_deterministic.json"
# Only these two files may be run; --catalog picks one by name, never by free path.
CATALOGS = {
    "deterministic": CANDIDATE,
    "paraphrases": ROOT / "evals" / "security_pyrit" / "candidate_paraphrases.json",
}
LEDGER = ROOT / "evals" / "runs" / "redteam_ledger.jsonl"
EXPECTED_STATUS = "candidate_pending_human_review"
DEFAULT_MAX_USD = 2.0  # owner-approved ceiling for the whole PyRIT pilot (2026-10-25)


def load_candidate(path: Path = CANDIDATE) -> tuple[dict[str, Any], list[EvalCase]]:
    """Materialize the candidate as ``EvalCase`` objects, failing closed."""
    catalog = json.loads(path.read_text(encoding="utf-8"))
    if catalog.get("status") != EXPECTED_STATUS:
        raise ValueError(f"unexpected candidate status: {catalog.get('status')!r}")
    cases: list[EvalCase] = []
    seen: set[str] = set()
    for raw in catalog["cases"]:
        case_id = raw["id"]
        expected = raw["expected"]
        if case_id in seen:
            raise ValueError(f"duplicate case id: {case_id}")
        seen.add(case_id)
        if not case_id.startswith("security_pyrit."):
            raise ValueError(f"unexpected case id: {case_id}")
        if not expected.get("response_criteria"):
            # Without criteria a safe_response case could only "pass" by not calling a
            # forbidden tool, which is not evidence of resistance (specs/049).
            raise ValueError(f"case without response_criteria: {case_id}")
        cases.append(
            EvalCase(
                case_id=case_id,
                category="security_pyrit",
                input_text=raw["input"],
                synthetic_context=dict(raw.get("context", {})),
                expected_outcome=expected["outcome"],
                required_tool=expected.get("required_tool"),
                forbidden_tools=frozenset(expected.get("forbidden_tools", [])),
                requires_user_confirmation=expected["requires_user_confirmation"],
                response_criteria=tuple(expected["response_criteria"]),
            )
        )
    return catalog, cases


def select(cases: list[EvalCase], only: list[str] | None, converter: list[str] | None,
           limit: int | None, exclude: list[str] | None = None,
           exclude_cases: list[str] | None = None) -> list[EvalCase]:
    known = {c.case_id for c in cases}
    unknown = sorted(set(exclude_cases or []) - known)
    if unknown:
        # A typo would silently keep a case the operator meant to drop.
        raise ValueError(f"--exclude-case does not match any case: {unknown}")
    chosen = [c for c in cases if not only or c.case_id in set(only)]
    chosen = [c for c in chosen if c.case_id not in set(exclude_cases or [])]
    if converter:
        suffixes = tuple(f"__{name}" for name in converter)
        chosen = [c for c in chosen if c.case_id.endswith(suffixes)]
    if exclude:
        blocked = tuple(f"__{name}" for name in exclude)
        chosen = [c for c in chosen if not c.case_id.endswith(blocked)]
    return chosen[:limit] if limit else chosen


def append_ledger(entry: dict[str, Any]) -> None:
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    with LEDGER.open("a", encoding="utf-8") as file:
        file.write(json.dumps(entry, ensure_ascii=False) + "\n")


def pass_cost(summary: dict[str, Any]) -> float:
    """USD spent by one pass: what OpenRouter reported, else the fixed-rate estimate."""
    agent = summary["agent_cost_usd"]
    judge = summary["judge_cost_usd"]
    return (agent if agent is not None else summary["agent_cost_est_usd"]) + (
        judge if judge is not None else summary["judge_cost_est_usd"])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--run", action="store_true", help="launches real inference")
    parser.add_argument("--catalog", choices=sorted(CATALOGS), default="deterministic",
                        help="which candidate catalog to run (default: deterministic, phase A)")
    parser.add_argument("--case", action="append", help="case id, repeatable")
    parser.add_argument("--converter", action="append",
                        help="only variants of this converter (e.g. base64), repeatable")
    parser.add_argument("--limit", type=int, help="first N selected cases (small first batch)")
    parser.add_argument("--exclude-converter", action="append",
                        help="drop variants of this converter (e.g. base64), repeatable")
    parser.add_argument("--exclude-case", action="append",
                        help="drop one case id after human review, repeatable; the ledger "
                             "records which ones were excluded")
    parser.add_argument("--provider-guardrail", choices=["block", "flag", "off"],
                        help="state of OpenRouter's prompt-injection guardrail for this key "
                             "during the run; required with --run and recorded in the ledger "
                             "(declared by the operator, the script cannot verify it)")
    parser.add_argument("--repeat", type=int, default=1,
                        help="consecutive passes; each appends its own ledger line")
    parser.add_argument("--max-usd", type=float, default=DEFAULT_MAX_USD,
                        help="ceiling for the whole invocation, accumulated across passes")
    parser.add_argument("--no-judge", action="store_true")
    parser.add_argument("--case-timeout", type=float, default=240.0)
    args = parser.parse_args(argv)
    if args.repeat < 1:
        parser.error("--repeat must be at least 1")
    if args.run and args.provider_guardrail is None:
        # Batches with and without the provider filter measure different things;
        # never let a real run be recorded without saying which one it was.
        parser.error("--provider-guardrail is required with --run")

    # ``load_candidate()`` keeps its no-argument default for the phase A catalog.
    catalog, cases = (load_candidate() if args.catalog == "deterministic"
                      else load_candidate(CATALOGS[args.catalog]))
    try:
        cases = select(cases, args.case, args.converter, args.limit, args.exclude_converter,
                       args.exclude_case)
    except ValueError as error:
        parser.error(str(error))
    print(f"candidate: {len(cases)} cases selected (pyrit {catalog.get('pyrit_version')}, "
          f"seed {catalog.get('random_seed')})")
    if not args.run:
        print("dry run: nothing inferred; add --run to spend")
        return 0

    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    light.disable_telemetry()

    async def amain() -> None:
        # ``--max-usd`` is a ceiling for the WHOLE invocation: each pass starts from what
        # the previous ones spent, exactly as run_evals_light does with ``spent_before``.
        spent, all_passed = 0.0, True
        for number in range(1, args.repeat + 1):
            print(f"== pass {number}/{args.repeat} (spent so far {spent:.4f} USD) ==", flush=True)
            summary = await light.run_suite(args, cases, spent_before=spent)
            append_ledger(
                {
                    "catalog": "security_pyrit",
                    "catalog_file": args.catalog,
                    "catalog_status": catalog["status"],
                    "provider_guardrail": args.provider_guardrail,
                    "excluded_converters": args.exclude_converter or [],
                    "excluded_cases": args.exclude_case or [],
                    "converter_filter": args.converter or [],
                }
                | summary
            )
            print(json.dumps({k: v for k, v in summary.items() if k != "rows"},
                             ensure_ascii=False), flush=True)
            spent += pass_cost(summary)
            all_passed = all_passed and summary["passed"] == summary["cases"]
            if summary["stopped_by_budget"]:
                break
        sys.stdout.flush()
        # The lightweight runner exits this way: loop.close() hangs on Windows.
        os._exit(0 if all_passed else 1)

    asyncio.run(amain())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
