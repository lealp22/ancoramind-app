# Tasks — specs/029 / BL-13

> Ninguna tarea de este fichero está iniciada. Este incremento solo entrega
> el diseño (`spec.md` + este desglose). Orden de ejecución recomendado:
> T1 → T2 → (T3 y T5 en paralelo, ambos dependen de T1) → T4 → T6.

## T1 — Schema y migración

- [ ] Migración Alembic nueva (`00XX_dream_memory`) con las 4 tablas de
  `spec.md` §3: `dream_transcripts`, `dream_candidates`, `dream_cursor`,
  `dream_runs`. Índices: único en `dream_transcripts.interaction_id`, único
  parcial en `dream_candidates (user_id, category, key) WHERE status =
  'active'`, PK simple en `dream_cursor.user_id`.
- [ ] CHECK constraints para `category` (enum cerrado §3.3), `status` y
  `source` — fail-closed a nivel de base de datos, no solo en Pydantic.
- [ ] `migrations/init.sql` sincronizado (equivalente a head).
- [ ] Tests de migración (fresh install, upgrade, downgrade) siguiendo el
  patrón de `test_migrations.py` existente.
- **Listo cuando:** `alembic upgrade head` y `downgrade -1` limpios en
  PostgreSQL real; `ruff`/`mypy` no aplican (sin código Python todavía más
  allá de la migración).

## T2 — Captura en el camino de finalización

- [ ] `src/domain/dream/models.py` (`DreamTranscriptCreate`, cifrado
  reutilizando `TelegramPayloadCipher`/el mismo patrón que
  `SpeechTranscriptCipher` en `src/domain/speech/preparation.py` — no
  reinventar el cifrador).
- [ ] `src/repositories/dream.py::DreamRepository.capture_transcript(...)`.
- [ ] Cablear la escritura en `src/domain/interactions/processor.py::_run_agent`
  (ver `spec.md` §3.1 para el punto exacto). Decidir y documentar si va en
  la misma transacción que `_persist_response` o en un best-effort
  separado; en cualquier caso, un fallo aquí **nunca** debe marcar la
  interacción como fallida ni bloquear la respuesta al usuario.
- [ ] Excluir explícitamente: comandos (`parse_telegram_command` ya
  intercepta antes), respuestas de consentimiento (`_handle_consent_input`/
  `_handle_voice_consent`), voz con flag desactivado.
- [ ] Tests unit: captura ocurre solo en el camino de respuesta normal del
  Agent, nunca en comandos/consentimiento; truncado al tope de longitud;
  cifrado (no texto plano en los args de la query); un fallo de captura no
  propaga ni cambia el estado de la interacción.
- **Listo cuando:** unit tests verdes, Ruff/mypy limpios, ningún test
  existente de `processor.py` cambia de comportamiento observable (la
  captura es un efecto secundario, no debe alterar las respuestas al
  usuario ni los estados de interacción ya cubiertos).

## T3 — Worker y adaptador LLM 🔶 núcleo implementado localmente — 2026-10-09

- [x] `src/domain/dream/worker.py::DreamWorker` siguiendo la forma de
  `src/domain/reminders/worker.py` (gate, `run_once()`, purga inline,
  `run_forever()` con `try/except` por ciclo).
- [ ] `src/agent/lifecycle.py::install_dream_worker_lifespan` (mismo patrón
  que `install_reminder_worker_lifespan`), gate `DREAM_ENABLED` +
  `ancora_database_url`. **Diferido:** necesita un `DreamRepositoryPort`
  concreto sobre SQL real (T1/T2); cablearlo contra un stub hoy dejaría
  `DREAM_ENABLED` sin efecto real, así que se deja para cuando exista la
  migración.
- [x] Nueva ruta lógica `ancoramind-dream` en `RoutingConfig`
  (`src/domain/runtime_config/models.py`, capability `text` +
  `structured_output`), añadida a `bootstrap_runtime_configuration()` igual
  que `ancoramind-embeddings`/`ancoramind-vision`. **Decisión (resuelve la
  pregunta abierta de spec.md §8):** no hace falta un campo dedicado como
  `RuntimeConfiguration.speech` — Dream no tiene billing por duración, así
  que basta con la entrada en `routing.routes` + el `ExecutionBudget`
  genérico; no se tocó `canonical_config_json`, así que no aplica el test de
  compatibilidad de checksum legado (ese test cubre un campo opcional nuevo
  a nivel raíz, no una entrada más en un dict ya versionado).
- [x] `src/agent/dream_access.py::GovernedDreamConsolidationAdapter`.
  **Desviación deliberada del patrón de `document_extraction.py`/
  `document_embeddings.py`:** esos adaptadores caen a un contexto standalone
  con `bootstrap_runtime_configuration()` solo como *fallback transicional*
  cuando no hay run gobernado. Dream nunca tiene un run gobernado — es su
  único camino, siempre — así que usar el bootstrap ahí ignoraría en
  silencio cualquier alias de Gateway publicado y activado para
  `ancoramind-dream`. El adaptador construye su contexto desde
  `RuntimeConfigManager.snapshot()` (la configuración realmente activada),
  igual que hace `GovernedInteractionRunner` para un run real.
- [x] `prompts/skills/dream_consolidation.md` — instructions del Agent de
  consolidación, enmarcando transcripts y preferencias existentes como DATA
  no confiable, con el enum cerrado de categorías repetido explícitamente
  en el prompt (cinturón y tirantes junto al esquema Pydantic).
- [ ] Fijar umbral de lote/cadencia (spec.md §8) — vive en
  `DreamRepositoryPort.claim_eligible_batches`, que todavía no tiene
  implementación concreta (T1/T2).
- **Listo cuando:** unit tests del worker (con repos/LLM mockeados) y del
  adaptador (sin red real, mismo estilo que `test_speech_access.py`) verdes;
  Ruff/mypy limpios; `DREAM_ENABLED=false` por defecto no cambia el
  comportamiento de arranque de `src.main`. ✅ (ver evidencia abajo; el
  gate de arranque no aplica aún porque la lifecycle wiring está diferida).

**Evidencia:** `src/domain/dream/ports.py` (`DreamBatch`,
`DreamConsolidationPort`, `DreamRepositoryPort` — el worker solo depende de
estas formas, nunca de SQL concreto), `src/domain/dream/worker.py`,
`src/agent/dream_access.py`, `prompts/skills/dream_consolidation.md`, más la
ruta nueva en `bootstrap_runtime_configuration()`. Tests:
`tests/unit/test_dream_worker.py` (5, con ambos puertos mockeados —
aplica mutaciones por batch, registra fallo sin aplicar mutaciones, purga
incluso sin batches elegibles, el loop sigue tras una excepción de ciclo y
propaga `CancelledError` sin dormir indefinidamente) y
`tests/unit/test_dream_access.py` (5, con un `Model` real de Agno como en
`test_document_extraction_adapter.py` — usa el snapshot *activado*, no el
bootstrap; mapea contenido estructurado válido; mapea fallo de inferencia y
contenido inválido a resultados controlados sin fuga de detalle del
proveedor; falla cerrado si la ruta `ancoramind-dream` no existe en la
config, sin llamar al modelo). 970 unit tests (suite completa), Ruff y
`mypy src/` limpios.

## T4 — Servicio de promoción ✅ implementado localmente — 2026-10-09

- [x] `src/domain/dream/service.py::DreamPromotionService` — aplica la
  política de §4.1 de forma pura y testeable (sin I/O), recibe candidatos
  propuestos por el LLM + estado actual de `dream_candidates` del usuario,
  devuelve las mutaciones a aplicar (upsert/supersede/reject).
- [x] Validación fail-closed del enum de `category` (schema Pydantic,
  independiente del CHECK de BD de T1 — cinturón y tirantes).
- [x] Tests: explícito activa directo; implícito requiere 2 batches;
  corrección explícita supersede; categoría fuera del enum se descarta;
  conflicto con memoria canónica (fuera de alcance de Dream — Dream nunca
  toca tablas canónicas, el test documenta ese límite).
- **Listo cuando:** cobertura de los 5 casos de arriba en unit tests, sin
  dependencias de infraestructura; Ruff/mypy limpios.

**Evidencia:** `src/domain/dream/{__init__,models,service}.py` +
`tests/unit/test_dream_promotion_service.py` (11 tests). Además de los 5
casos pedidos se cubrieron 4 escenarios que la política de §4.1 deja
implícitos y que convenía fijar en código en vez de dejarlos ambiguos:
un signal implícito nunca sobrescribe un valor `active` (se rechaza,
auditado como fila `rejected`, el valor activo gana); reforzar un valor
`active` ya idéntico no genera escritura (no-op); una señal implícita
contradictoria antes de alcanzar el umbral reinicia el conteo
(`ResetCandidate`, no promueve con evidencia mezclada); una señal explícita
siempre gana aunque exista un `candidate` implícito pendiente para la misma
clave. También se añadieron dos resguardos defensivos: más de una fila
existente para el mismo `(category, key)` o más de una propuesta para la
misma clave en un mismo batch lanzan `ValueError` en vez de elegir un
ganador en silencio (si ocurre, es una violación de un invariante que debe
corregirse río arriba, no resolverse aquí). 960 unit tests passing (suite
completa), Ruff y `mypy src/` limpios.

## T5 — Tools de usuario (READ/forget) 🔶 tools implementadas, registro diferido — 2026-10-09

- [x] `src/agent/tools/dream.py`: `list_my_preferences` (READ, envuelve con
  `render_retrieved_records`/`untrusted_results` igual que `search_notes`;
  solo muestra preferencias `active`, nunca `candidate` tentativas).
- [x] `propose_preference_forget` / `execute_preference_forget` (DESTRUCTIVE,
  patrón estándar; soporta un `candidate_id` o "todas"). Añadido
  `"forget_dream_preference"` a `SUPPORTED_MUTATIONS`
  (`src/domain/actions/mutations.py`) para que el camino Core
  (`_execute_claimed`, voz/botón/«Sí» a secas) también pueda ejecutarlo sin
  pasar por el Agent — igual que el resto de capacidades gobernadas.
  `src/domain/dream/preferences.py::DreamPreferenceService` +
  `src/repositories/dream_candidates.py::DreamCandidatesRepository` (olvidar
  es un *soft delete* a `status='deleted'`, nunca se borra la fila — mismo
  principio de auditoría que el resto del diseño).
- [ ] Flag de opt-out durable por usuario (spec.md §8) — no implementado en
  este incremento; requiere decidir dónde vive la columna junto con T1.
- [ ] **Registro en `_init_domain_tools()` (`src/main.py`) — diferido
  deliberadamente.** La tabla `ancora.dream_candidates` no existe todavía
  (T1 sin migrar); registrar las tools ahora las dejaría activas y
  fallando contra una tabla inexistente en cuanto el LLM las invocara, no
  solo "sin implementar". Mismo criterio ya aplicado a la lifecycle wiring
  de T3. Registrar junto con T1.
- [x] `prompts/skills/dream.md` (skill del usuario, distinto del prompt
  interno de consolidación de T3) — cuándo usar `list_my_preferences`, cómo
  responder a "qué sabes de mí"/"olvida que prefiero X". **No añadido
  todavía a `assemble_instructions()`** — se conecta junto con el registro
  de tools diferido arriba.
- [x] Tests: `test_dream_candidates_repository.py` (8, sesión mockeada —
  mismo estilo que `test_repository_returning_guards.py`),
  `test_dream_preference_service.py` (5, incluida la distinción deliberada
  `bool False` vs `int 0` para no confundir "no encontrado" con "nada que
  olvidar"), `test_dream_tools.py` (9, mismo estilo que
  `test_note_tools.py`/`test_document_tools.py`).
- **Listo cuando:** tests verdes, Ruff/mypy limpios, tools visibles en
  `docs/architecture.md`/README (tabla de capabilities) tras actualizarla.
  **Pendiente de infra para cerrar del todo:** el registro en `main.py` y
  el flag de opt-out, ambos ligados a T1.

**Evidencia:** 22 tests nuevos (8+5+9) sobre lo ya existente. 1012 unit
tests pasando en los ficheros propios de este incremento (dos fallos
observados en `test_runtime_config_models.py`/`test_speech_access.py`
corresponden a cambios sin commitear de otra sesión trabajando en BL-34 en
paralelo — no relacionados con T5, confirmado excluyendo esos ficheros).
Ruff y `mypy src/` limpios en todo lo tocado por este incremento.

## T6 — Sincronización de documentación

- [ ] `docs/architecture.md` §7: fila "Soft Personal" → `AncoraMind Core` /
  `PostgreSQL (ancora)` (ya anotado en spec.md §6 de la decisión; aquí solo
  se ejecuta cuando T1-T5 estén implementadas, no antes).
- [ ] `BACKLOG.md` BL-13: marcar como implementado con fecha, evidencia de
  tests y recuento de tools (siguiendo el estilo de cierre de otros BL-*).
- [ ] `README.md` tabla de capabilities (si existe, confirmar con
  `docs/architecture.md`).
- **Listo cuando:** no hay afirmaciones "pendiente"/"futuro" sobre memoria
  personal que ya estén implementadas (mismo tipo de hallazgo que BL-40
  Fase 6).
