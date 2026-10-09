# Tasks — specs/030 / BL-34

> Orden recomendado: T1 → T2 → T3 → T4 → T5 → T6. T1-T4 son dominio puro o
> wiring testeable con mocks; ninguna requiere PostgreSQL/Docker.

## T1 — Estimación de tokens y modelos de política

- [ ] `src/domain/context_policy/models.py`: `estimate_tokens(text: str) -> int`
      (heurística `len // 4`, documentada como aproximación — spec.md §3).
- [ ] `ContextBudgetConfig` (spec.md §5.1) y `ContextWindowDecision`
      (spec.md §5.2) como modelos Pydantic/`dataclass(frozen=True)` puros.
- [ ] Tests: `estimate_tokens` con texto vacío, unicode, texto largo.
- **Listo cuando:** Ruff/mypy limpios, sin dependencias de infraestructura.

## T2 — Runtime config: `context_window_tokens` + `context_budget`

- [ ] `LogicalRoute.context_window_tokens: int | None` (spec.md §4).
- [ ] `RuntimeConfiguration.context_budget: ContextBudgetConfig | None = None`.
- [ ] `bootstrap_runtime_configuration()` fija valores explícitos para
      `ancoramind-default`/`ancoramind-fast`/`ancoramind-vision`/
      `ancoramind-dream`; `ancoramind-embeddings` queda en `None`.
- [ ] Test de compatibilidad: una `RuntimeConfiguration` ya persistida sin
      estos campos sigue validando (`model_validate`) y, si existe un fixture
      de checksum anterior en los tests actuales, no cambia su valor cuando
      los campos nuevos están ausentes/`None` (mismo patrón que la nota de
      `canonical_config_json` sobre `speech`).
- **Listo cuando:** tests de `test_runtime_config_models.py` (o el fichero
  equivalente existente) cubren el caso aditivo; Ruff/mypy limpios.

## T3 — Política de selección de historial

- [ ] `src/domain/context_policy/service.py`:
      `select_history_window(turns, *, available_for_history_tokens) ->
      ContextWindowDecision` (spec.md §5.2).
- [ ] `resolve_num_history_runs(decision, *, floor=1, ceiling=10) -> int`
      (spec.md §5.3).
- [ ] `resolve_history_ceiling(context_window_tokens, execution_budget,
      context_budget) -> int` (spec.md §6) — la función que
      `GovernedAgentFactory` llamará en T4, sin leer ninguna sesión real.
- [ ] Tests: historial que cabe entero, historial que requiere truncar,
      turno individual mayor que todo el presupuesto disponible, ventana
      `None` (fallback conservador), ventana grande vs. pequeña → ceilings
      distintos dentro de `[1, 10]`.
- **Listo cuando:** los 5 casos de spec.md §10.1 tienen test; Ruff/mypy
  limpios.

## T4 — Wiring en `GovernedAgentFactory`

- [ ] `GovernedAgentFactory.create_for_run()` sustituye `num_history_runs=10`
      fijo por `resolve_history_ceiling(...)` usando la ruta resuelta y el
      snapshot del run (spec.md §6).
- [ ] Nuevo atributo de telemetría `ancora.context.outcome` añadido a
      `SPAN_ATTRIBUTE_ALLOWLIST`/`METRIC_ATTRIBUTE_ALLOWLIST`
      (`src/observability/telemetry.py`) — emitido como metadata-only, sin
      contenido ni tamaños de texto reales (spec.md §9). Decidir en
      implementación si se emite desde la factory o desde el runner; debe
      ser consistente con el patrón ya usado por
      `ancora.document.extraction_route`.
- [ ] Tests de regresión en `tests/unit/test_agent_llm_access.py` (o nuevo
      fichero `test_governed_agent_factory_context.py`): una ruta con
      `context_window_tokens` grande obtiene un `num_history_runs` mayor que
      una con ventana pequeña; el valor nunca excede 10 ni baja de 1.
- [ ] Test de privacidad: el nuevo atributo no transporta contenido (mismo
      patrón que `tests/unit/test_observability_privacy.py`).
- **Listo cuando:** `test_agent_llm_access.py` existente sigue en verde sin
  cambios de comportamiento no relacionados; Ruff/mypy limpios.

## T5 — Contrato de compactación diferido (sin activar)

- [ ] `src/domain/context_policy/compaction.py::CompactionPort` (Protocol,
      spec.md §7) — solo la interfaz, sin implementación física ni wiring a
      `LLMAccess` en este incremento.
- [ ] `select_history_window` degrada `needs_compaction` a `truncated`
      cuando no se le pasa ningún `CompactionPort` (comportamiento por
      defecto de este incremento).
- [ ] Test: `needs_compaction` sin compactor configurado → `outcome` final
      observable es `truncated`, con los turnos sobrantes descartados.
- **Listo cuando:** el contrato está definido y testeado, pero no activado;
  no se crea ninguna ruta lógica nueva en `bootstrap_runtime_configuration()`
  para compactación (`ancoramind-dream` ya existe por BL-13 y no se reusa
  aquí sin decisión explícita futura).

## T6 — Documentación y cierre

- [ ] `BACKLOG.md` BL-34: marcar como implementado localmente con fecha,
      referencia a `specs/030`, recuento de tests y limitaciones conocidas
      (§8 de spec.md) — siguiendo el estilo de cierre de BL-38/BL-41.
- [ ] Registrar como pendiente separado (nuevo ítem o nota dentro de BL-34)
      el housekeeping de retención/purga de `agno_runtime`, explícitamente
      fuera de este incremento (spec.md §8).
- [ ] `docs/architecture.md` — no requiere cambio salvo que la tabla de §7
      (tres tipos de memoria) necesite una nota aclaratoria distinguiendo
      memoria de trabajo (BL-34) de "Conversation/Runtime"; evaluar al cerrar.
- **Listo cuando:** no quedan afirmaciones "pendiente"/"futuro" en
  BACKLOG.md sobre lo que este incremento sí entrega (política + wiring);
  la compactación real sigue correctamente marcada como no implementada.
