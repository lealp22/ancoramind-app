# 049 · Evals ligeros y elección de juez (Span-02)

> Estado: experimento del juez hecho (2026-10-23). Runner ligero operativo y probado
> en `tool_selection` y `response_style` (2026-10-24); suite completa pendiente.
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
  Sirve para descartar un juez malo, no para fijar una tasa de acierto.
- No se probó Cloudflare Clef: OpenRouter avisa de truncado ~2.000 tokens de
  `state` en Workers AI. Tampoco Decider V1.2.
- El juez va directo a OpenRouter, no por el Gateway (decisión de capstone:
  datos sintéticos; el Gateway está pensado para chat). No aplica a producción.
- Primer intento falló con 401 (clave inválida): sin cobro ni conclusiones.
- Resultados brutos en `tmp/judge_bench.json` (ignorado por Git).

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
Cada fila guarda además `failures` (textos de las comprobaciones de código: nombres
de tools y resultados, sin contenido). La primera entrada del ledger (SHA `11188f1`)
tiene tokens a 0 por el bug descrito abajo; no es un dato real.
Pendiente: informe agregado y gráfica de evolución en el dashboard.

## Estado de cada caso

| Estado | Significado |
|---|---|
| `pass` | Código OK y el juez da pass a todos los criterios |
| `fail` | Falla una comprobación de código o el juez da fail a algún criterio |
| `review` | Código OK pero algún criterio es `uncertain` o dio error: revisión humana |
| `unevaluated` | Caso `clarify`/`safe_response` ejecutado sin juez (`--no-judge`): no hay forma de comprobar el texto |
| `error` | El caso no llegó a ejecutarse |

Casos `clarify` y `safe_response`: el código sólo ve qué tools se llamaron, no el texto
(límite documentado en `eval_physical_executor.py`). El runner ignora ese desajuste de
resultado y decide el juez; siguen valiendo tools prohibidas y confirmación.

## Qué ve el juez

Se le pasa `answer` y `proposal_text` por separado, tal como los produce el Agent. Los
criterios de propuestas distinguen ambos campos. Antes se mezclaba el bloque del Core
dentro de `answer` y el juez suspendía por "repetir" datos que el Agent no repetía
(`single_proposal`, `mixed_read_proposal`). Con la separación pasan.

También recibe `propuestas_persistidas_por_el_core` (nº de propuestas creadas en el run,
medido por código). Motivo: en `pending_write` el juez suspendía "no dice que ya se haya
creado" porque no puede saber que la propuesta existe. Con el dato el criterio pasa de
fail (p=0,03) a uncertain; **no resuelve el caso**, y el campo no se validó en el banco
de 18 criterios (cambio no calibrado).

## Bug de tokens y coste (corregido en `a5a4a31`)

`GovernedModel` leía `response.input_tokens`, pero Agno deja el uso en
`response.response_usage`. Los tokens llegaban vacíos al ledger de uso del Agent (el
bot de producción usa el mismo código; las filas históricas de uso LLM probablemente
también estaban vacías, **sin verificar** en la BD). Arreglo: `_usage_tokens` lee primero
el atributo directo y, si falta, `response_usage`; 2 tests nuevos. El coste
(`agent_cost_usd`) sigue en `null` mientras la configuración no tenga tarifas
(`pricing=None`): los tokens son la referencia.

## Primeras ejecuciones reales (2026-10-23/24, una ejecución por caso)

| Ejecución | Resultado | Nota |
|---|---|---|
| `tool_selection` (3) | 3/3 pass | ~14.500 tokens de entrada por caso |
| `response_style` (12), runner inicial | 6 pass, 3 review, 3 fail | `answer` mezclado con el bloque del Core |
| idem, `answer`/`proposal_text` separados | 9 pass, 1 review, 2 fail | |
| idem, + dato de propuestas y catálogo corregido | 11 pass, 1 review | `pending_write` en review |

Gasto del juez por tanda: ~0,00008 USD. Hay ruido entre ejecuciones (un criterio
uncertain cambió de caso en cada tanda): las cifras son una foto, no una tasa estable.

## Cambio de catálogo

`response_style.document_explicit_id`: `required_tool` de `get_document` a
`search_documents`. El usuario da el nombre, no el ID, así que `get_document` no se puede
llamar sin buscar antes; `search_documents` ya devuelve el ID verificado. El esquema sólo
admite una tool requerida, por eso no se pudo expresar "una u otra". Es un cambio de
referencia (golden) decidido por el propietario.

## Pendiente

- Suite completa dentro de `--max-usd` y repetir ejecuciones para medir el ruido.
- Validar `propuestas_persistidas_por_el_core` en el banco del juez o retirarlo.
- Informe agregado y gráfica de evolución en el dashboard.
