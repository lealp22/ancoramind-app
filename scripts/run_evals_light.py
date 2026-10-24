"""Evals ligeros: Agent real + tools simuladas, checks por código y juez Span-02.

Sin ledger/sesión: se ejecuta en local contra el código actual. Por defecto es un
ensayo (no infiere); `--run` lanza inferencia real. Cada ejecución añade UNA línea
sin contenido (tokens, coste, veredictos) a evals/runs/ledger.jsonl.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import httpx  # noqa: E402

from scripts import judge_bench  # noqa: E402
from src.agent.eval_core_consent_executor import CoreConsentEvalExecutor  # noqa: E402
from src.agent.evals import (  # noqa: E402
    EvalCase,
    EvalExecutionRequest,
    evaluate_observation,
    load_eval_cases,
)
from src.domain.llm_access.models import LlmUsageEventCreate  # noqa: E402

LEDGER = ROOT / "evals" / "runs" / "ledger.jsonl"
JUDGE_MODEL = "respan/span-02"
SECOND_OPINION = "openai/gpt-6-luna-decisions"
SEMANTIC_OUTCOMES = frozenset({"clarify", "safe_response"})
CORE_CATEGORY = "confirmation"  # lo resuelve el harness Core, sin LLM (specs/018 T6b)
# Casos que el runner ligero no puede ejecutar: motivo por caso.
EXCLUDED_CASES = {
    # El executor crea el adjunto como application/octet-stream y Agno sólo admite
    # una lista cerrada de MIME: falla con ValidationError antes de llamar al modelo.
    "documents.attachment_is_analyzed_once",
    # OpenRouter bloquea la petición con 403 ("prompt injection patterns detected")
    # por la frase literal "Ignore previous instructions": el modelo nunca ve el caso.
    # El texto no se reformula: lo fijan los tests de recall de la heurística (BL-39).
    "security.document_prompt_injection_is_data",
    "security.web_snippet_instruction_is_data",
}


AGENT_PRICE_IN_PER_M = 0.10   # USD/M tokens de entrada: ESTIMACIÓN (catálogo OpenRouter
AGENT_PRICE_OUT_PER_M = 0.50  # 2026-10-18, GPT-6 Luna); no es la factura real.


def estimate_agent_cost(usage: dict[str, Any]) -> float:
    """Coste estimado del Agent: el ledger de uso no trae coste (pricing=None)."""
    return (usage["input_tokens"] * AGENT_PRICE_IN_PER_M
            + usage["output_tokens"] * AGENT_PRICE_OUT_PER_M) / 1_000_000


class UsageCollector:
    """Recoge tokens/coste por llamada del Agent (solo metadatos, sin contenido)."""

    def __init__(self) -> None:
        self.events: list[LlmUsageEventCreate] = []

    async def __call__(self, event: LlmUsageEventCreate) -> None:
        self.events.append(event)

    def take(self) -> dict[str, Any]:
        events, self.events = self.events, []
        cost = [e.actual_cost if e.actual_cost is not None else e.estimated_cost
                for e in events]
        return {
            "model_calls": len(events),
            "input_tokens": sum(e.input_tokens or 0 for e in events),
            "output_tokens": sum(e.output_tokens or 0 for e in events),
            "cost_usd": None if any(c is None for c in cost) else round(sum(cost), 6),
        }


def build_executor(collector: UsageCollector):
    """Agent real vía AgnoLLMAccess + OpenRouter directo (aceptado en capstone)."""
    from src.agent.eval_physical_executor import GovernedPhysicalEvalExecutor
    from src.agent.llm_access import AgnoLLMAccess
    from src.config import Settings

    settings = Settings()
    settings.litellm_proxy_enabled = False
    access = AgnoLLMAccess(settings=settings, usage_recorder=collector)
    return GovernedPhysicalEvalExecutor(llm_access=access)


def judge_state(case: EvalCase, answer: str, proposal_text: str = "",
                persisted_proposals: int | None = None) -> dict[str, Any]:
    state: dict[str, Any] = {
        "peticion_del_usuario": case.input_text, "contexto": dict(case.synthetic_context),
        "respuesta_answer": answer, "respuesta_proposal_text": proposal_text}
    if persisted_proposals is not None:
        # Hecho objetivo medido por el código: el juez no puede verlo en el texto.
        state["propuestas_persistidas_por_el_core"] = persisted_proposals
    return state


def judge_case(client: httpx.Client, key: str, case: EvalCase, answer: str,
               proposal_text: str, model: str,
               persisted_proposals: int | None = None) -> tuple[list[dict[str, Any]], int]:
    """Un `noul` por criterio. Devuelve (veredictos, tokens de entrada)."""
    verdicts, tokens = [], 0
    for index, criterion in enumerate(case.response_criteria):
        item = {"state": judge_state(case, answer, proposal_text, persisted_proposals),
                "criterion": criterion}
        try:
            p, used = judge_bench.ask(client, key, model, item)
        except (httpx.HTTPError, KeyError, ValueError):
            verdicts.append({"criterion": index, "p": None, "verdict": "error"})
            continue
        tokens += used
        verdicts.append({"criterion": index, "p": round(p, 3),
                         "verdict": judge_bench.verdict(p)})
    return verdicts, tokens


async def run_case(executor: Any, case: EvalCase, route: str, revision: int,
                   collector: UsageCollector, timeout: float = 240.0) -> dict[str, Any]:
    request = EvalExecutionRequest(case=case, logical_route=route, config_revision=revision)
    started = time.monotonic()
    try:
        observation = await asyncio.wait_for(executor.execute(request), timeout=timeout)
    except Exception as error:  # noqa: BLE001 - un caso roto no debe parar la suite
        diagnostic = getattr(error, "diagnostic", None)
        return {"case_id": case.case_id, "category": case.category, "status": "error",
                "error": type(error).__name__,
                **({"terminal": diagnostic.model_dump()} if diagnostic else {}),
                "usage": collector.take(),
                "seconds": round(time.monotonic() - started, 1)}
    result = evaluate_observation(request, observation)
    failures = list(result.failures)
    if case.expected_outcome in SEMANTIC_OUTCOMES and case.category != CORE_CATEGORY:
        # clarify/safe_response solo se distinguen leyendo el texto: decide el juez.
        # En `confirmation` el resultado lo fija el Core de forma determinista.
        failures = [f for f in failures if not f.startswith("outcome expected")]
    return {"case_id": case.case_id, "category": case.category,
            "status": "pass" if not failures else "fail",
            "failures": failures, "tools": list(result.observed_tool_names),
            "usage": collector.take(), "seconds": round(time.monotonic() - started, 1),
            "_answer": (observation.reply.answer if observation.reply else "") or "",
            "_proposal_text": (getattr(observation.reply, "proposal_text", "")
                               if observation.reply else "") or "",
            "_persisted": sum(1 for p in (observation.proposals or ())
                              if p.get("created_this_run"))}


def settle_status(row: dict[str, Any], case: EvalCase, judged: bool) -> None:
    """Combina comprobaciones de código y juez en el estado final del caso."""
    if row["status"] != "pass":
        return
    verdicts = [j["verdict"] for j in row.get("judge", [])] if judged else []
    if "fail" in verdicts:
        row["status"] = "fail"
    elif (case.expected_outcome in SEMANTIC_OUTCOMES and case.category != CORE_CATEGORY
          and not judged):
        row["status"] = "unevaluated"  # sin juez no hay forma de comprobar el texto
    elif any(v != "pass" for v in verdicts):
        row["status"] = "review"  # juez incierto o con error: revisión humana



def append_ledger(entry: dict[str, Any]) -> None:
    """Registro append-only sin contenido: qué se evaluó, tokens y coste."""
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    with LEDGER.open("a", encoding="utf-8") as file:
        file.write(json.dumps(entry, ensure_ascii=False) + "\n")


def git_sha() -> str:
    import subprocess
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT,
                              capture_output=True, text=True, timeout=10).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return "unknown"


async def run_suite(args: argparse.Namespace, cases: list[EvalCase],
                    spent_before: float = 0.0) -> dict[str, Any]:
    collector = UsageCollector()
    executor = build_executor(collector)
    core_executor = CoreConsentEvalExecutor()
    route, revision = "ancoramind-default", executor._snapshot.revision  # noqa: SLF001
    key = os.environ.get("OPENROUTER_API_KEY", "")
    judge_tokens, rows, stopped = 0, [], False
    with httpx.Client(timeout=60, follow_redirects=False, trust_env=False) as client:
        for case in cases:
            spent = spent_before + sum(estimate_agent_cost(r["usage"]) for r in rows) + (
                judge_tokens * judge_bench.PRICES[JUDGE_MODEL] / 1_000_000)
            if spent >= args.max_usd:
                print(f"tope_alcanzado {spent:.4f} USD: casos restantes sin ejecutar")
                stopped = True
                break
            row = await run_case(core_executor if case.category == CORE_CATEGORY else executor,
                                 case, route, revision, collector, args.case_timeout)
            answer = row.pop("_answer", "")
            proposal_text = row.pop("_proposal_text", "")
            persisted = row.pop("_persisted", 0)
            judged = bool(case.response_criteria) and row["status"] != "error" \
                and not args.no_judge
            if judged:
                row["judge"], used = judge_case(client, key, case, answer, proposal_text,
                                                JUDGE_MODEL, persisted)
                judge_tokens += used
            settle_status(row, case, judged)
            rows.append(row)
            print(f"{row['status']:5} {case.case_id} {row['seconds']}s", flush=True)
    agent_cost = [r["usage"]["cost_usd"] for r in rows]
    judge_cost = round(judge_tokens * judge_bench.PRICES[JUDGE_MODEL] / 1_000_000, 6)
    return {
        "ts": datetime.now(UTC).isoformat(timespec="seconds"), "git_sha": git_sha(),
        "agent_model": os.environ.get("LLM_MODEL", ""), "judge_model": JUDGE_MODEL,
        "cases": len(rows), "passed": sum(r["status"] == "pass" for r in rows),
        "agent_input_tokens": sum(r["usage"]["input_tokens"] for r in rows),
        "agent_output_tokens": sum(r["usage"]["output_tokens"] for r in rows),
        "agent_cost_usd": None if any(c is None for c in agent_cost) else round(
            sum(agent_cost), 6),
        "agent_cost_est_usd": round(sum(estimate_agent_cost(r["usage"]) for r in rows), 6),
        "stopped_by_budget": stopped,
        "judge_input_tokens": judge_tokens, "judge_cost_usd": judge_cost, "rows": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true", help="lanza inferencia real")
    parser.add_argument("--category", action="append", help="repetible; por defecto todas")
    parser.add_argument("--case", action="append", help="id de caso, repetible")
    parser.add_argument("--no-judge", action="store_true")
    parser.add_argument("--max-usd", type=float, default=0.30,
                        help="para antes del siguiente caso si el gasto ESTIMADO lo supera "
                             "(acumulado entre repeticiones)")
    parser.add_argument("--repeat", type=int, default=1,
                        help="pasadas seguidas; cada una añade su línea al ledger")
    parser.add_argument("--case-timeout", type=float, default=240.0,
                        help="segundos máximos por caso (un caso colgado no bloquea la suite)")
    args = parser.parse_args()
    cases = load_eval_cases(categories=set(args.category) if args.category else None)
    cases = [c for c in cases if not args.case or c.case_id in set(args.case)]
    # `confirmation` va al harness Core (determinista, sin LLM); en el resto, los casos
    # de consentimiento no son ejecutables por el Agent, que no tiene `execute_*`.
    cases = [c for c in cases if c.case_id not in EXCLUDED_CASES]
    cases = [c for c in cases if c.category == CORE_CATEGORY or (
        c.expected_outcome != "confirm_pending_action"
        and not (c.required_tool or "").startswith("execute_"))]
    if not args.run:
        print(f"ensayo: {len(cases)} casos seleccionados; añade --run para inferir")
        return 0
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    async def amain() -> None:
        total, all_passed = 0.0, True
        for number in range(1, args.repeat + 1):
            print(f"== pasada {number}/{args.repeat} (gasto estimado acumulado "
                  f"{total:.4f} USD) ==", flush=True)
            summary = await run_suite(args, cases, spent_before=total)
            # Registro dentro del bucle: loop.close() se cuelga en Windows.
            append_ledger({k: v for k, v in summary.items() if k != "rows"} | {
                "rows": summary["rows"]})
            print(json.dumps({k: v for k, v in summary.items() if k != "rows"},
                             ensure_ascii=False), flush=True)
            total += summary["agent_cost_est_usd"] + summary["judge_cost_usd"]
            all_passed = all_passed and summary["passed"] == summary["cases"]
            if summary["stopped_by_budget"]:
                break
        sys.stdout.flush()
        os._exit(0 if all_passed else 1)

    asyncio.run(amain())
    return 0


if __name__ == "__main__":
    sys.exit(main())

