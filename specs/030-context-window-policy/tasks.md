# Tasks — specs/030 / BL-34

> Orden recomendado: T1 → T2 → T3 → T4 → T5 → T6. T1-T4 son dominio puro o
> wiring testeable con mocks; ninguna requiere PostgreSQL/Docker.

## T1 — Estimación de tokens y modelos de política ✅

- [x] `src/domain/context_policy/models.py`: `estimate_tokens(text: str) -> int`
      (heurística `len // 4`, documentada como aproximación — spec.md §3).
- [x] `ContextBudgetConfig` (spec.md §5.1) y `ContextWindowDecision`
      (spec.md §5.2) como modelos Pydantic/`dataclass(frozen=True)` puros.
- [x] Tests: `estimate_tokens` con texto vacío, unicode, texto largo.
- **Listo cuando:** Ruff/mypy limpios, sin dependencias de infraestructura.

## T2 — Runtime config: `context_window_tokens` + `context_budget` ✅

- [x] `LogicalRoute.context_window_tokens: int | None` (spec.md §4).
- [x] `RuntimeConfiguration.context_budget: ContextBudgetConfig | None = None`.
- [x] `bootstrap_runtime_configuration()` fija valores explícitos para
      `ancoramind-default`/`ancoramind-fast`/`ancoramind-vision`/
      `ancoramind-dream`; `ancoramind-embeddings` queda en `None`.
- [x] Test de compatibilidad: una `RuntimeConfiguration` ya persistida sin
      estos campos sigue validando (`model_validate`) y, si existe un fixture
      de checksum anterior en los tests actuales, no cambia su valor cuando
      los campos nuevos están ausentes/`None` (mismo patrón que la nota de
      `canonical_config_json` sobre `speech`).
- **Listo cuando:** tests de `test_runtime_config_models.py` (o el fichero
  equivalente existente) cubren el caso aditivo; Ruff/mypy limpios.

## T3 — Política de selección de historial ✅

- [x] `src/domain/context_policy/service.py`:
      `select_history_window(turns, *, available_for_history_tokens) ->
      ContextWindowDecision` (spec.md §5.2).
- [x] `resolve_num_history_runs(decision, *, floor=1, ceiling=10) -> int`
      (spec.md §5.3).
- [x] `resolve_history_ceiling(context_window_tokens, execution_budget,
      context_budget) -> int` (spec.md §6) — la función que
      `GovernedAgentFactory` llamará en T4, sin leer ninguna sesión real.
- [x] Tests: historial que cabe entero, historial que requiere truncar,
      turno individual mayor que todo el presupuesto disponible, ventana
      `None` (fallback conservador), ventana grande vs. pequeña → ceilings
      distintos dentro de `[1, 10]`.
- **Listo cuando:** los 5 casos de spec.md §10.1 tienen test; Ruff/mypy
  limpios.

## T4 — Wiring en `GovernedAgentFactory` ✅ — 2026-10-09

- [x] `GovernedAgentFactory.create_for_run()` sustituye `num_history_runs=10`
      fijo por `resolve_history_ceiling(...)` usando la ruta resuelta y el
      snapshot del run (spec.md §6).
- [x] Nuevo atributo de telemetría `ancora.context.outcome` añadido a
      `SPAN_ATTRIBUTE_ALLOWLIST`/`METRIC_ATTRIBUTE_ALLOWLIST`
      (`src/observability/telemetry.py`) — emitido como metadata-only, sin
      contenido ni tamaños de texto reales (spec.md §9). **Decisión:** se
      emite desde la propia factory (no desde el runner), mismo punto donde
      ya se resuelve el techo — consistente con el patrón de
      `ancora.document.extraction_route`. Como la factory nunca lee el
      historial real (§6), el outcome aquí es una aproximación binaria:
      `fits_entirely` cuando la ventana permitió conservar el techo estándar
      (10), `truncated` en caso contrario; `needs_compaction` no se emite
      nunca desde esta capa (no hay `CompactionPort` conectado — T5).
- [x] Tests de regresión en `tests/unit/test_governed_agent_factory_context.py`
      (nuevo fichero): una ruta con `context_window_tokens` grande obtiene un
      `num_history_runs` mayor que una con ventana pequeña; el valor nunca
      excede 10 ni baja de 1; ventana `None` cae al fallback conservador.
- [x] Test de privacidad en `test_observability_privacy.py`
      (`test_context_outcome_metadata_is_a_bounded_allowlisted_enum`): el
      nuevo atributo no transporta contenido.
- **Listo cuando:** `test_agent_llm_access.py` existente sigue en verde sin
  cambios de comportamiento no relacionados; Ruff/mypy limpios. ✅

## T5 — Contrato de compactación diferido (sin activar) ✅ — 2026-10-09

- [x] `src/domain/context_policy/compaction.py::CompactionPort` (Protocol,
      spec.md §7) — solo la interfaz (+ `CompactionOutcome`), sin
      implementación física ni wiring a `LLMAccess` en este incremento.
- [x] `select_history_window` acepta un `compactor: CompactionPort | None =
      None` opcional (nunca invocado) y degrada `needs_compaction` a
      `truncated` cuando no se pasa ninguno (comportamiento por defecto de
      este incremento).
- [x] Tests: `test_select_history_window_requires_compaction_for_older_turns`
      (con un `_FakeCompactor` — `needs_compaction` solo aparece si hay
      compactor) y `test_select_history_window_degrades_to_truncated_without_a_compactor`
      (`outcome` final observable es `truncated`, turnos sobrantes
      descartados, sin compactor).
- **Listo cuando:** el contrato está definido y testeado, pero no activado;
  no se crea ninguna ruta lógica nueva en `bootstrap_runtime_configuration()`
  para compactación (`ancoramind-dream` ya existe por BL-13 y no se reusa
  aquí sin decisión explícita futura). ✅

## T6 — Documentación y cierre ✅ — 2026-10-09

- [x] `BACKLOG.md` BL-34: marcado como implementado localmente con fecha,
      referencia a `specs/030`, recuento de tests y limitaciones conocidas
      (§8 de spec.md) — siguiendo el estilo de cierre de BL-38/BL-41.
- [x] Registrado como pendiente separado (nota dentro de BL-34) el
      housekeeping de retención/purga de `agno_runtime`, explícitamente
      fuera de este incremento (spec.md §8).
- [x] `docs/architecture.md` — evaluado: no requiere cambio: la tabla de
      memoria ya distingue runtime/conversacional (Agno) de canónica
      (`ancora`), y esta política solo acota cuánto de la primera se reenvía
      al modelo por turno — no introduce un tercer tipo de memoria nuevo.
- **Listo cuando:** no quedan afirmaciones "pendiente"/"futuro" en
  BACKLOG.md sobre lo que este incremento sí entrega (política + wiring);
  la compactación real sigue correctamente marcada como no implementada. ✅
  1084 unit tests, Ruff y `mypy src/` (154 ficheros) limpios.
