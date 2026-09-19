# Spec: 014 — Agentic Evals Foundation

> **Backlog:** BL-8
> **Status:** in progress (2026-09-19)
> **Target:** datasets de comportamiento versionados y validados localmente para
> detectar regresiones de prompts, descripciones de tools y modelos.

---

## Requirement

AncoraMind necesita una suite evaluable antes de ampliar capacidades o cambiar
instrucciones/modelos. La gobernanza ya exige categorías para selección de tools,
documentos, vehículos, confirmación y seguridad, pero `evals/` estaba vacío.

### Must Have

- Un formato de casos versionado y legible en Git, sin dependencias nuevas.
- Casos sintéticos para las cinco categorías: `tool_selection`, `documents`,
  `vehicle`, `confirmation` y `security`.
- Cada caso declara una expectativa observable: tool requerida, aclaración,
  confirmación de propuesta pendiente o respuesta segura; también tools vetadas
  y si el siguiente paso requiere confirmación humana.
- Runner local determinista que valida estructura, cobertura y ausencia de
  secretos obvios sin llamar a LLMs, tools ni servicios externos.
- Tests unitarios y documentación de uso.

### Won't Have (este incremento)

- Llamadas a un modelo real, scoring semántico de respuestas o costes de inferencia.
- Ejecutar tools, propuestas, escrituras, Telegram o Railway durante las evals.
- Guardar prompts, respuestas o contenido de usuario en telemetría.

## Design

```text
evals/<category>/cases.json (datos sintéticos, Git)
        ↓
scripts/run_evals.py (stdlib: carga + validación de contrato)
        ↓
resumen reproducible / exit code CI
```

JSON se elige para evitar añadir un parser YAML al producto. El contrato v1 deja
`context` como objeto sintético para que una futura fase pueda materializar un
run gobernado sin cambiar los datasets. Esa futura fase sólo podrá capturar
metadata permitida por specs/013.

## Success Criteria

1. `python scripts/run_evals.py` valida los cinco catálogos y produce un resumen.
2. Hay al menos tres casos sintéticos por categoría (15 casos iniciales).
3. Un catálogo mal formado, incompleto o contradictorio falla con exit code != 0.
4. `pytest tests/unit/test_eval_catalog.py` y Ruff pasan.
5. Cambios de prompts/modelos/tools tienen una guía concreta para revisar los
   casos afectados; las evals LLM reales se dejan como siguiente incremento.