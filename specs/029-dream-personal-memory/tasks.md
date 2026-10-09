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

## T3 — Worker y adaptador LLM

- [ ] `src/domain/dream/worker.py::DreamWorker` siguiendo la forma de
  `src/domain/reminders/worker.py` (gate, `run_once()`, purga inline,
  `run_forever()` con `try/except` por ciclo).
- [ ] `src/agent/lifecycle.py::install_dream_worker_lifespan` (mismo patrón
  que `install_reminder_worker_lifespan`), gate `DREAM_ENABLED` +
  `ancora_database_url`.
- [ ] Nueva ruta lógica `ancoramind-dream` en `RoutingConfig`
  (`src/domain/runtime_config/models.py`) — capability `text`. Confirmar si
  requiere también un campo de configuración dedicado (como
  `RuntimeConfiguration.speech`) o basta con la ruta + budget genérico; test
  de compatibilidad de checksum legado como el que ya existe para `speech`
  (`test_legacy_config_checksum_stays_compatible` en
  `tests/unit/test_speech_access.py`) si se añade un campo nuevo al nivel
  raíz.
- [ ] `src/agent/dream_access.py::GovernedDreamConsolidationAdapter`
  (análogo a `AgnoDocumentExtractionAdapter`), contexto standalone como
  `GovernedDocumentEmbeddingAdapter._standalone_context`.
- [ ] `prompts/skills/dream_consolidation.md` — instructions del Agent de
  consolidación, enmarcando los transcripts como DATA no confiable.
- [ ] Fijar umbral de lote/cadencia (spec.md §8) y documentarlo aquí una vez
  decidido.
- **Listo cuando:** unit tests del worker (con repos/LLM mockeados) y del
  adaptador (sin red real, mismo estilo que `test_speech_access.py`) verdes;
  Ruff/mypy limpios; `DREAM_ENABLED=false` por defecto no cambia el
  comportamiento de arranque de `src.main`.

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

## T5 — Tools de usuario (READ/forget)

- [ ] `src/agent/tools/dream.py`: `list_my_preferences` (READ, envuelve con
  `render_retrieved_records`/`untrusted_results` igual que `search_notes`).
- [ ] `propose_preference_forget` / `execute_preference_forget` (DESTRUCTIVE,
  patrón estándar; soporta un `candidate_id` o "todas"; soporta fijar el
  flag de opt-out — ver spec.md §8 para dónde vive esa columna, a decidir
  aquí).
- [ ] Registro en `_init_domain_tools()` (`src/main.py`).
- [ ] `prompts/skills/dream.md` (skill del usuario, distinto del prompt
  interno de consolidación de T3) — cuándo usar `list_my_preferences`, cómo
  responder a "qué sabes de mí"/"olvida que prefiero X".
- [ ] Tests: patrón de los 8 tests parametrizados de T4.8/BL-40 que
  confirman que `execute_preference_forget` se niega a mutar sin
  `confirm_or_use_confirmed`.
- **Listo cuando:** tests verdes, Ruff/mypy limpios, tools visibles en
  `docs/architecture.md`/README (tabla de capabilities) tras actualizarla.

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
