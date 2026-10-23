# 049 · Evals ligeros y elección de juez (Span-02)

> Estado: experimento del juez hecho (2026-10-23). Runner ligero pendiente.
> Contexto: el arnés de specs/040–045 se aparca para el capstone (producto en
> cambio continuo; el ámbito congelado por sesión bloqueaba cada iteración).
> No se borra ni se modifica: `ancoramind-evals` queda idle.

## Decisión

Evals ligeros ejecutables en local: checks deterministas por código (tools,
confirmación) + juez *decisions* para `response_style`. **Juez por defecto:
`respan/span-02`**; `openai/gpt-6-luna-decisions` como segunda opinión.

## Experimento

- Script: `scripts/judge_bench.py` (sin ledger; tope duro por modelo y 1 USD total).
- Datos: 18 criterios etiquetados de `evals/response_style/provisional_labels.json`.
- Endpoint: `POST https://openrouter.ai/api/alpha/decisions`, pregunta `noul` por
  criterio. Veredicto en código: p≥0,8 pass; p≤0,2 fail; resto uncertain.
- Etiquetas humanas: `pass`/`fail`; `ambiguous` se espera como `uncertain`.
- Una ejecución por modelo, 2026-10-23. Datos sintéticos, sin contenido personal.

| Juez | Coinciden | Falsos pass | Uncertain | Gasto USD |
|---|---|---|---|---|
| gpt-6-luna-decisions | 15/18 | 0 | 1 | 0,000494 |
| span-02 | 15/18 | 0 | 1 | 0,000041 |
| jev-1.14 | 14/18 | 0 | 4 | 0,000326 |

Desacuerdos: los tres dan pass a `brief_question.ambiguous#1` (p 0,94–1,0; la
etiqueta humana es discutible). Luna: 1 uncertain donde el humano puso pass y
`uncertainty.ambiguous#2` como fail. Span-02: `uncertainty.bad#2` uncertain
(p 0,21) y `uncertainty.ambiguous#2` pass (p 0,84). Jev: 3 uncertain donde el
humano puso pass (más abstención, menos aciertos en español).

## Por qué Span-02

1. Iguala a Luna en aciertos y falsos pass (0) con unas 12× menos coste de entrada
   (0,01 frente a 0,10 USD/M tokens).
2. Está orientado a evaluación/guardrails de salidas de LLM (ficha OpenRouter).
3. Jev, referencia por interés académico (System One), es el más prudente pero
   deja más trabajo manual y su idioma óptimo es el inglés (docs TypeSafe).
4. Sus errores van en dirección segura salvo un pass dudoso (0,84): por eso Luna
   revisa los casos con p entre 0,8 y 0,9.

## Límites (no sobreinterpretar)

- n=18, etiquetas provisionales del autor, umbrales sin calibrar, una ejecución.

## Runner ligero (`scripts/run_evals_light.py`)

```
python scripts/run_evals_light.py                          # ensayo, sin inferencia
python scripts/run_evals_light.py --run --category tool_selection
python scripts/run_evals_light.py --run --case response_style.uncertainty
```

- Agent real (`GovernedPhysicalEvalExecutor`) con tools simuladas; checks por
  código (`evaluate_observation`) y, si hay `response_criteria`, Span-02 por criterio.
- Excluye los casos de consentimiento (requieren el harness Core, specs/018).
- `--max-usd` (0,30 por defecto) para antes del siguiente caso; `--no-judge` omite el juez.
- El Agent va directo a OpenRouter con tu `.env` (sin Gateway): decisión de capstone.

## Registro de evaluaciones

Cada `--run` añade una línea a `evals/runs/ledger.jsonl` (versionable): fecha, SHA de
Git, modelos, casos/aprobados, tokens y coste del Agent y del juez, y por caso
estado, tools, uso, duración y veredicto por criterio. **Sin prompts ni
respuestas.** Si OpenRouter no devuelve coste, `agent_cost_usd` queda `null` y los
tokens sirven de referencia (no se inventa un precio).
Pendiente: informe agregado y gráfica de evolución en el dashboard.

  Sirve para descartar un juez malo, no para fijar una tasa de acierto.
- No se probó Cloudflare Clef: OpenRouter avisa de truncado ~2.000 tokens de
  `state` en Workers AI. Tampoco Decider V1.2.
- El juez va directo a OpenRouter, no por el Gateway (decisión de capstone:
  datos sintéticos; el Gateway está pensado para chat). No aplica a producción.
- Primer intento falló con 401 (clave inválida): sin cobro ni conclusiones.
- Resultados brutos en `tmp/judge_bench.json` (ignorado por Git).
