# Tasks — Spec 018: Isolated Agentic Evals Execution Harness

> **Backlog:** BL-8 · abierto 2026-09-27

- [x] T1 · Definir el aislamiento: no reutilizar el runner Telegram/ledger ni
      tools de producción; contextos sintéticos son DATA, nunca autoridad.
- [x] T2 · Materializar catálogos v1 validados en casos tipados y crear un
      puerto executor asíncrono inyectable.
- [x] T3 · Implementar checks deterministas de outcome, tool requerida/vetada y
      confirmación, con proyección metadata-only.
- [x] T4 · Añadir unit tests con executor fake que demuestren la ausencia de
      inputs/contextos/respuestas en el reporte.
- [x] T5 · Actualizar documentación y BACKLOG.
- [x] T6 · Adaptador físico implementado (2026-10-03):
      `src/agent/eval_physical_executor.py::GovernedPhysicalEvalExecutor` +
      catálogo de tools simuladas en `src/agent/eval_tools.py`. Agent
      gobernado por `LLMAccess` inyectado, `RuntimeConfigSnapshot`/budget de
      evaluación separados (bootstrap, sin PostgreSQL), sin reutilizar
      `GovernedAgentFactory` (acoplado a history/db de producción). Probado
      con un `Model` scripted en memoria (sin red/coste) —
      `tests/unit/test_eval_tools.py` + `tests/unit/test_eval_physical_executor.py`.
      **Decisión documentada:** `outcome` sólo deriva de las tools realmente
      invocadas; un sentinel `no_tool_call` sustituye a `clarify`/
      `safe_response` cuando no se invoca ninguna tool, porque distinguir
      esos dos requiere juzgar el texto de respuesta semánticamente — eso es
      T8, no T6. Detalle en `verification.md`.
- [ ] T7 · Con credenciales y presupuesto aprobados, ejecutar la modalidad LLM
      fuera de CI por defecto y capturar evidencia metadata-only.
- [ ] T8 · Definir/calibrar scoring semántico opcional (Jev u otro juez) con
      etiquetas humanas sintéticas y baseline por ruta/configuración.
- [ ] T6b · Tras el cierre legacy (BL-39/40, 2026-10-11), trasladar los casos
      de confirmación a un harness Core y actualizar expectativas. El adaptador
      Agent ya los rechaza antes de inferencia y no expone ejecutoras; no contar
      ese rechazo como un éxito de la evaluación de consentimiento.
