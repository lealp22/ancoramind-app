"""Comparativa puntual de jueces 'decisions' de OpenRouter (capstone, sin ledger).

Usa las etiquetas sintéticas de evals/response_style/provisional_labels.json.
Una pregunta `noul` por criterio; el umbral lo aplica este script.
Tope de gasto duro por ejecución (--max-usd); la clave sale de .env, nunca se imprime.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
URL = "https://openrouter.ai/api/alpha/decisions"
# USD por millón de tokens de entrada (salida gratis), según la ficha de OpenRouter.
PRICES = {
    "openai/gpt-6-luna-decisions": 0.10,
    "respan/span-02": 0.01,
    "typesafe/jev-1.14": 0.042,
}
PASS_AT, FAIL_AT = 0.8, 0.2


def load_items() -> list[dict]:
    """Un item por criterio etiquetado: estado para el juez + etiqueta humana."""
    base = ROOT / "evals" / "response_style"
    cases = {c["id"]: c for c in json.loads(
        (base / "cases.json").read_text(encoding="utf-8"))["cases"]}
    labels = json.loads((base / "provisional_labels.json").read_text(encoding="utf-8"))
    items = []
    for example in labels["examples"]:
        case = cases[example["case_id"]]
        for index, label in zip(example["criterion_indices"], example["labels"], strict=True):
            items.append({
                "id": f"{example['id']}#{index}",
                "label": label,
                "state": {
                    "peticion_del_usuario": case["input"],
                    "contexto": case["context"],
                    "respuesta_answer": example["reply"]["answer"],
                    "respuesta_proposal_text": example["reply"]["proposal_text"],
                },
                "criterion": case["expected"]["response_criteria"][index],
            })
    return items



def verdict(probability: float) -> str:
    if probability >= PASS_AT:
        return "pass"
    if probability <= FAIL_AT:
        return "fail"
    return "uncertain"


def ask(client: httpx.Client, key: str, model: str, item: dict) -> tuple[float, int]:
    """Devuelve (probabilidad de cumplimiento, tokens de entrada)."""
    body = {
        "model": model,
        "state": item["state"],
        "questions": {"cumple": {
            "type": "noul",
            "instructions": (
                "Juzga la respuesta del asistente (`respuesta_answer` y "
                "`respuesta_proposal_text`) frente a este criterio: "
                + item["criterion"]
            ),
            "criteria": {
                "true": "La respuesta cumple el criterio.",
                "false": "La respuesta incumple el criterio o lo contradice.",
            },
        }},
    }
    response = client.post(URL, json=body, headers={"Authorization": f"Bearer {key}"})
    response.raise_for_status()
    data = response.json()
    return float(data["answers"]["cumple"]["noul"]), int(data["usage"]["input_tokens"])


def run_model(model: str, items: list[dict], key: str, budget: float) -> dict:
    spent, rows = 0.0, []
    with httpx.Client(timeout=60, follow_redirects=False, trust_env=False) as client:
        for item in items:
            # Cota previa: no se lanza otra llamada si el tope ya está alcanzado.
            if spent >= budget:
                rows.append({**item, "p": None, "got": "no_run"})
                continue
            try:
                p, tokens = ask(client, key, model, item)
            except (httpx.HTTPError, KeyError, ValueError) as error:
                status = getattr(getattr(error, "response", None), "status_code", None)
                rows.append({**item, "p": None, "got": "error",
                             "error": f"{type(error).__name__}:{status}"})
                continue
            spent += tokens * PRICES[model] / 1_000_000
            rows.append({**item, "p": p, "got": verdict(p)})
    return {"model": model, "spent_usd": round(spent, 6), "rows": rows}


def expected(label: str) -> str:
    return {"pass": "pass", "fail": "fail"}.get(label, "uncertain")


def summarize(result: dict) -> dict:
    rows = [r for r in result["rows"] if r["got"] in {"pass", "fail", "uncertain"}]
    agree = sum(r["got"] == expected(r["label"]) for r in rows)
    false_pass = sum(r["got"] == "pass" and r["label"] == "fail" for r in rows)
    abstain = sum(r["got"] == "uncertain" for r in rows)
    return {"model": result["model"], "judged": len(rows),
            "of": len(result["rows"]), "agree": agree,
            "false_pass": false_pass, "uncertain": abstain,
            "spent_usd": result["spent_usd"]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--models", nargs="+", default=list(PRICES))
    parser.add_argument("--max-usd", type=float, default=0.25,
                        help="tope por modelo; el total nunca supera 1 USD")
    parser.add_argument("--out", default="tmp/judge_bench.json")
    args = parser.parse_args()
    if args.max_usd * len(args.models) > 1.0:
        print("tope_total_superior_a_1_usd")
        return 2
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    key = os.environ.get("OPENROUTER_API_KEY", "")
    if not key:
        print("falta_OPENROUTER_API_KEY")
        return 2
    items = load_items()
    results = [run_model(m, items, key, args.max_usd) for m in args.models]
    out = ROOT / args.out
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    for result in results:
        print(json.dumps(summarize(result), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())

