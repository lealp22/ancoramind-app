# Spec: 018 — Isolated Agentic Evals Execution Harness

> **Backlog:** BL-8
> **Status:** en curso (2026-09-27)
> **Target:** ejecutar los casos sintéticos versionados contra un executor
> inyectado y aislado, comprobando por código los gates de gobernanza antes de
> cualquier scoring semántico o inferencia real.

---

## Contexto

La spec 014 dejó intencionalmente el runner como validación estática. El
`GovernedInteractionRunner` de producción no puede reutilizarse para evals: está
acoplado a identidad Telegram, ledger durable, outbox y tools de dominio que
pueden tocar PostgreSQL o ejecutar acciones gobernadas.

Este incremento introduce un harness sin wiring físico. Materializa únicamente
fixtures sintéticas ya validadas y delega la ejecución en un puerto inyectado.

## Must Have

- Cargar los catálogos v1 después de su validación estática y materializar casos
  sintéticos tipados.
- Puerto asíncrono de executor aislado que reciba `input`, `context` sintético,
  ruta lógica y revisión de configuración.
- Checks deterministas para outcome, tool requerida, tools prohibidas y estado
  de confirmación humana.
- Reporte metadata-only que no incluya input, context ni response text.
- Tests unitarios con executors fake; sin provider, base de datos, Telegram,
  AgentOS ni tools de producción.

## Won't Have

- Crear un Agent, provider, `LLMAccess`, Gateway o sesión de base de datos.
- Ejecutar las tools reales, propuestas, mutaciones o acciones externas.
- Persistir respuestas, inputs o contextos de las evals.
- Activar un comando de CI que invoque inferencia pagada.
- Scoring semántico/Jev, baseline o compatibilidad física Gateway.

## Design

```text
evals/*/cases.json ──> validación spec 014 ──> EvalCase
                                              │
 executor inyectado (futuro: LLMAccess + tools simuladas) ──> EvalObservation
                                              │
                                      checks deterministas
                                              │
                         EvalCaseResult en memoria ──> metadata-only report
```

`context` es DATA sintética no confiable. El executor físico futuro debe fijar
una identidad de evaluación separada y usar exclusivamente doubles/simuladores
de tools; no puede derivar permisos, propuestas pendientes o confirmación desde
el contexto del catálogo.

## Success Criteria

1. Los 19 casos actuales se materializan tras la validación existente.
2. Una tool prohibida, la ausencia de una requerida, outcome distinto o una
   confirmación incorrecta producen un fallo determinista independiente del
   texto de respuesta.
3. El reporte no contiene input, context ni respuesta.
4. Las suites unitarias y Ruff siguen verdes.
5. Una integración física futura requiere una task posterior: `LLMAccess`,
   snapshot/budget propios de eval, tools simuladas y autorización explícita de
   credenciales/presupuesto.