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

## T7 — Compactación real activada, vía el ledger propio (no `CompactionPort`) ✅ — 2026-10-12

El propietario propuso un gate barato (contador de tokens acumulados por
sesión, ya devueltos por cada llamada al LLM) para activar la compactación
sin pagar en cada mensaje el I/O que T5/§6 evitó deliberadamente (leer la
sesión completa de Agno). Investigado y confirmado antes de implementar:
`ancora.llm_usage_events.total_tokens` ya existe por llamada; solo faltaba
indexar `telegram_interactions.agno_session_id`.

- [x] Migración `0013_session_token_index` (índice) + `init.sql`
      sincronizado — no validada contra PostgreSQL real en esta sesión.
- [x] `LlmUsageRepository.sum_session_tokens(session_id)` — `SUM` indexado,
      nunca lee contenido.
- [x] **Decisión de diseño que diverge del contrato T5:** `CompactionPort`/
      `CompactionOutcome` seguían pensados para turnos reales de Agno
      (`ConversationTurn`, opacos) — exactamente el I/O que §6 evitó. Este
      incremento define un contrato nuevo, más simple,
      `SessionSummarizationPort`/`SessionExchange`/`SessionSummaryOutcome`
      (`src/domain/context_policy/session_summary.py`), sobre el **ledger
      propio de AncoraMind** (mensaje del usuario + respuesta final del
      Agent, ya cifrados en `telegram_interactions`/`logical_responses`) —
      nunca la tabla interna de Agno. `CompactionPort` queda sin usar,
      documentado como tal, no borrado.
- [x] `TelegramInteractionsRepository.list_session_exchanges(session_id)` —
      ciphertext crudo oldest-first; el llamador descifra con el mismo
      `TelegramPayloadCipher` ya usado en todo el procesador.
- [x] `oldest_fraction_count(total, ratio)` (`context_policy/service.py`) —
      pura, cuántos intercambios antiguos compactar (ratio configurable,
      40% por defecto, pedido por el propietario; conserva al menos uno).
- [x] `GovernedContextCompactionAdapter` (`src/agent/context_compaction_access.py`)
      — mismo patrón standalone-context que `GovernedDreamConsolidationAdapter`
      (specs/029 T3), nueva ruta lógica dedicada `ancoramind-context-compaction`.
      **Corrige un gap encontrado en Dream al replicar su patrón:**
      `dream_access.py` nunca abre `execution_context_scope` antes de
      `agent.arun()` — con un modelo real gobernado eso lanzaría
      `GovernanceViolationError`; este adaptador sí lo abre (patrón correcto
      ya usado en `document_extraction.py`). No se corrige `dream_access.py`
      en este incremento — anotado aparte en BACKLOG.md.
- [x] `InteractionProcessor._maybe_compact_context()` — gate barato primero
      (cero queries con el flag apagado o bajo umbral); solo si se cruza el
      umbral lee y descifra el tramo antiguo y pide el resumen. Un fallo del
      compactor degrada a `(None, None)` sin abortar el run.
- [x] `GovernedAgentFactory.create_for_run(..., compaction_summary=,
      reduced_history_runs=)` — el resumen se añade como bloque extra de
      `instructions` para ese run; nunca se persiste.
- [x] Config: `CONTEXT_COMPACTION_ENABLED` (false por defecto),
      `CONTEXT_COMPACTION_TOKEN_THRESHOLD`, `CONTEXT_COMPACTION_RATIO`.
- [x] Tests: `test_llm_usage_repository.py`,
      `test_interactions_repository_session_exchanges.py`,
      `test_context_compaction_access.py`, ampliados
      `test_governed_agent_factory_context.py` y
      `test_interaction_processor.py` (15 tests nuevos en total).
- **Listo cuando:** con el flag apagado el comportamiento es idéntico al de
  T1-T6 (cero queries nuevas); con el flag activo y el umbral cruzado, se
  compacta de verdad vía LLM sin tocar `agno_runtime`. ✅ 1310 unit tests,
  Ruff y `mypy src/` (166 ficheros) limpios. **Pendiente:** validar el
  índice contra PostgreSQL real y un E2E con una sesión larga de verdad
  (bloqueado por infraestructura, igual que el resto del pipeline).
