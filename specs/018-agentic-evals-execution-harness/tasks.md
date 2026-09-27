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
- [ ] T6 · Diseñar e implementar el adaptador físico: Agent gobernado por
      `LLMAccess`, `RuntimeConfigSnapshot`/budget de evaluación separados y
      catálogo de tools simuladas sin I/O.
- [ ] T7 · Con credenciales y presupuesto aprobados, ejecutar la modalidad LLM
      fuera de CI por defecto y capturar evidencia metadata-only.
- [ ] T8 · Definir/calibrar scoring semántico opcional (Jev u otro juez) con
      etiquetas humanas sintéticas y baseline por ruta/configuración.