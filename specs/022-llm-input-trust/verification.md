# Verificación — Spec 022 / BL-39

> Estado: verificación local parcial y diagnóstico remoto de solo lectura
> (2026-10-11); rollout de consentimiento y evals LLM reales pendientes.
> La evidencia fechada inferior conserva la historia de incrementos anteriores.

## Corrección del bypass legacy — 2026-10-11

Se retiran `execute_*` del Agent gobernado/singleton y eval Agent; las APIs
legacy de confirmación/reutilización/auditoría rechazan sin I/O. Flag OFF no
habilita ejecución legacy. `ProposalExecutor` es la única vía de ejecución.
1263 unit + 144 integration passed (1 live STT skipped), Ruff/mypy limpios;
sin inferencia real. Prueba de integración nueva verifica claim humano real,
rechazo legacy antes/después del claim y una sola ejecución Core sin replay.
Evidencia y límites: `../023-audit-remediation/operational-review-2026-10-11.md`.
Los párrafos históricos sobre `confirm_or_use_confirmed` describen el camino
anterior, no el comportamiento actual. BL-39 no se cierra por esta corrección.

**Incremento posterior 2026-10-11:** `answerCallbackQuery` completado localmente,
1300 unit/155 integration passed (1 live STT skipped), cobertura 79.46%.
El acuse no concede autoridad y su fallo no repite una acción. E2E pendiente;
detalle en `../023-audit-remediation/callback-acknowledgement.md`. Las referencias
históricas inferiores a "answerCallbackQuery pendiente" quedan superadas por
este incremento, no por una validación visual de producción.

## T8 — frontera de adjuntos gobernada acotada — 2026-10-14

La ruta gobernada ya archivaba y procesaba `ResolvedTelegramMedia` antes de
crear el Agent principal; por tanto no entrega bytes, URLs ni `files=`/`images=`
de Telegram a `agent.arun()`. La revisión local detectó que el resumen JSON
`untrusted_data` de un lote podía todavía crecer hasta ~18 KB con diez
extracciones máximas y se concatenaba completo al input del Agent.

Se añadió un tope agregado de **6000 caracteres** exclusivamente a la proyección
transitoria `telegram_attachment_ingestion`: se conservan sólo registros
completos que quepan, el JSON sigue siendo parseable y `records_omitted` refleja
los omitidos. El documento/resultado canónico ya archivado no se modifica. Como
defensa adicional, `GovernedInteractionRunner` valida prefijo, JSON, `trust`,
`source`, lista de records y longitud antes de anexar el bloque; un resultado
malformado, plano o sobredimensionado se descarta del prompt, sin reenviar los
bytes originales.

Pruebas nuevas cubren un lote de diez adjuntos con filename/resumen adversarial,
el límite agregado y los sobres inválidos (`trust` incorrecto, records no-lista,
texto plano y tamaño excesivo). No prueba obediencia semántica de un modelo ni
la ruta visual real de Telegram.

Evidencia focalizada:

```powershell
.venv\Scripts\python.exe -m ruff check src/agent/tools/untrusted_results.py src/agent/tools/documents.py src/agent/governed_interaction_runner.py tests/unit/test_document_tools.py tests/unit/test_governed_interaction_runner.py tests/unit/test_instructions.py
.venv\Scripts\python.exe -m mypy src/agent/tools/untrusted_results.py src/agent/tools/documents.py src/agent/governed_interaction_runner.py
.venv\Scripts\python.exe -m pytest tests/unit/test_document_tools.py tests/unit/test_governed_interaction_runner.py tests/unit/test_instructions.py tests/unit/test_document_extraction_port.py -q
.venv\Scripts\python.exe scripts/run_evals.py
git diff --check
```

- 81 pruebas focalizadas superadas.
- Ruff/mypy focalizados limpios.
- Catálogo estático: 36 casos válidos en seis categorías.
- Sin LLM real, red, Docker, PostgreSQL, migración ni datos productivos.

## Ejecución local

```powershell
python -m pytest tests/unit/ -q
ruff check src/ tests/ scripts/ migrations/
mypy src/
python scripts/run_evals.py
git diff --check
```

2026-09-29: `pytest tests/unit/ -q` → **514 passed** (incluye 5 tests nuevos
del incremento); `ruff check src/ tests/ scripts/ migrations/` → limpio;
`mypy src/` → limpio (105 archivos); `python scripts/run_evals.py` → catálogo
válido, 19 casos / 6 categorías; `git diff --check` → limpio. Los tests
intentaron exportar trazas/métricas a `localhost:4318` sin Collector y dieron
avisos de conexión; ningún test falló. No se ejecutó integration ni E2E al
no disponer de infraestructura. La validación del catálogo no ejecuta el Agent.

2026-09-30: segundo incremento local (lectura de notas/documentos + 8 fixtures
sintéticos nuevos). `python -m pytest tests/unit/ -q` → **521 passed**;
`ruff check src/ tests/ scripts/ migrations/` → limpio;
`mypy src/` → limpio (106 archivos); `python scripts/run_evals.py` →
catálogo válido, 27 casos / 6 categorías (11 security);
`git diff --check` → limpio. Los tests usan servicios simulados, comprueban
framing JSON, procedencia, límites, dato benigno útil, Unicode, falsos cierres,
no eco de query/ID, no mutación de datos originales y cobertura estática del
corpus. Avisos de OpenTelemetry al intentar enviar trazas a `localhost:4318`
sin Collector local; sin fallos de tests. Sin integration/E2E ni Agent/LLM real;
**validar el JSON del corpus no mide resistencia a prompt injection**.

## Pendiente

- 2026-09-30: diseño P0 acordado en `consent-design.md` (UX «Sí» solo para una
  propuesta presentada, ID explícito para varias, TTL 15 minutos, evidencia
  durable vinculada al evento posterior y política sin replay ambiguo).
  Añadido parser **sin conectar** a `src/domain/interactions/consent_intent.py`:
  23 nuevos unit tests de frases aisladas e identificadores, **no es prueba de
  autenticación ni autoriza operaciones**. `python -m pytest tests/unit/ -q`
  → **544 passed**; `python -m ruff check src/ tests/ scripts/ migrations/`
  → limpio; `python -m mypy src/` → limpio (107 módulos);
  `python scripts/run_evals.py` → 27 casos / 6 categorías;
  `git diff --check` → limpio. Exportador OTel advierte de ausencia de
  Collector en `localhost:4318`. Sin migración, guard conectado,
  integration ni E2E en este incremento: **P0 y BL-39 siguen abiertos**.
- Validar el comportamiento real de los modelos y la ruta multimodal del
  Agent principal con un harness aislado; las unit tests prueban contratos
  de serialización, no inmunidad semántica a prompt injection.
- No se han realizado E2E ni cambios operativos/remotos.

## P0 — implementado (specs/023-audit-remediation, Fase 4)

2026-10-02: T6b/T7 del diseño P0 se implementaron y verificaron localmente
como parte de `specs/023-audit-remediation` (T4.1–T4.8), detrás del flag
`GOVERNED_CONSENT_ENABLED` (`Settings.governed_consent_enabled`, **apagado
por defecto en producción**). Resumen (detalle completo en
`specs/023-audit-remediation/tasks.md` y `verification.md`):

- Migración `0006_proposal_consent` con el modelo de estados de
  `consent-design.md` (`pending_confirmation → confirmed → executing →
  executed | failed_definitive | failed_ambiguous`, más `expired`/`discarded`),
  CHECK de estados, `payload_hash` y procedencia (`source_interaction_id`,
  `bot_id`, `chat_id`).
- `ActionProposalsRepository`: nueva API de consentimiento
  (`claim_confirmation`, `begin_execution`, `complete_execution`,
  `discard_pending_for_chat`, `list_confirmable`, `mark_presented`) que nunca
  hace commit por sí misma — el llamador controla la transacción.
- `InteractionProcessor._handle_consent_input` resuelve botones
  `c:<uuid>`/`d:<uuid>` y «Sí»/«Sí <UUID>» **antes** de comandos y del Agent,
  reutilizando el mismo outbox durable que una respuesta normal. `/new`
  invoca `discard_pending_for_chat` (hueco real encontrado en T4.8: el
  método existía desde T4.1 pero no tenía caller).
- `confirm_or_use_confirmed()` nuevo en el repositorio: intenta el `confirm()`
  legacy primero (comportamiento sin cambios con el flag apagado — el bot
  sigue funcionando hoy en producción vía el criterio del LLM, decisión
  explícita del propietario); si la propuesta ya quedó `confirmed` por el
  claim pre-Agent, la reutiliza sin que el LLM la autorice. Aplicado a los
  8 `execute_*` existentes: `execute_vehicle`, `execute_vehicle_maintenance`,
  `execute_reminder`, `execute_calendar_event`, `execute_todo_list`,
  `execute_todo_item`, `execute_note`, `execute_document_delete`.
- `remember_note` (el único WRITE directo sin propuesta) sustituido por
  `propose_note`/`execute_note`. `propose_document_delete`/
  `execute_document_delete` nuevas — cierran el hueco de que no existía
  ninguna tool de borrado de documentos.
- **Excepción aprobada y documentada** (no un bypass sin registrar):
  `analyze_document`/`DocumentService.ingest` siguen siendo automáticos —
  AGENTS.md §2.4 y `docs/governance.md` explican la justificación de UX.
- Tests: 17 de integración en `test_proposal_consent.py` (ciclo completo,
  un solo uso, **carrera real entre dos sesiones con un solo ganador**, 6
  rechazos parametrizados, ventana que no se amplía, `/new`, fallo ambiguo
  terminal, CHECK de estados, regresión de `mark_executed`) + 2 de
  migración + 5 unitarios de modelo + 8 parametrizados
  (`TestExecuteWithoutAConfirmedProposal`, uno por cada `execute_*`) + 1
  test de integración end-to-end nuevo para `/new`.
- Resultados finales (2026-10-02): `pytest tests/unit/ -q` → **622 passed**;
  `pytest tests/integration/ -q` → **94 passed**; `ruff check src/ tests/
  scripts/ migrations/` → limpio; `mypy src/` → limpio (112 módulos);
  `python scripts/run_evals.py` → 27 casos / 6 categorías (actualizado
  `remember_note` → `propose_note`/`execute_note` en
  `evals/security/cases.json`); `git diff --check` → limpio.

**Lo que sigue sin cerrar P0 por completo:** el flag está apagado en
producción (decisión explícita, para no romper el bot mientras se valida);
`answerCallbackQuery` no está conectado al sender real de Telegram (el botón
mantiene su reloj de carga); y T8/T9 (procedencia en el resto de tools,
corpus adversarial ejecutado contra el Agent real) siguen pendientes, igual
que antes de este incremento.
