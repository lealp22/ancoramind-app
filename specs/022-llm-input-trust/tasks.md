# Tareas — Spec 022 / BL-39

## Primer incremento: verificable localmente

- [x] T1 · Definir frontera, alcance y contrato P0 sin simular consentimiento
      por LLM; documentar limitaciones y criterios de aceptación.
- [x] T2 · Mover instrucciones de extracción a `prompts/` y versionar prompt.
- [x] T3 · Serializar fuente no confiable de extracción y acotar filename/texto;
      testear delimitadores, saltos de línea, Unicode, binario y ruta visual.
- [x] T4 · Retirar `suggested_actions` de las salidas de tools documentales,
      conservando el campo persistido; testear ambas tools.
- [x] T5 · Ejecutar suite completa de unit, Ruff, mypy y evals; registrar
      resultados en `verification.md`.

## Diseño P0 acordado, implementación pendiente

- [x] T6a · Documentar en `consent-design.md` UX de «Sí» inequívoco / `Sí <UUID>`,
      TTL, prueba de entrega y evento posterior, estados, fallos ambiguos,
      inventario de mutaciones y ruta legacy. Diseño, no control implementado.
- [x] T6b · **Implementado (2026-10-02) en `specs/023-audit-remediation`
      Fase 4 (T4.1–T4.8), detrás de `GOVERNED_CONSENT_ENABLED`
      (`Settings.governed_consent_enabled`, apagado por defecto):**
      migración `0006_proposal_consent` (estados `consent-design.md` +
      procedencia + `payload_hash`); `ActionProposalsRepository.claim_confirmation`
      /`begin_execution`/`complete_execution`/`discard_pending_for_chat` sin
      commit propio (transacción del llamador); `InteractionProcessor.
      _handle_consent_input` resuelve botones `c:<uuid>`/`d:<uuid>` y «Sí»/
      «Sí <UUID>» antes de comandos y Agent; `confirm_or_use_confirmed`
      aplicado a los 8 `execute_*` (vehicle, vehicle_maintenance, reminder,
      calendar_event, todo_list, todo_item, note, document_delete) — ya no
      queda ningún WRITE directo sin propuesta (`remember_note` → `propose_note`
      /`execute_note`; `propose_document_delete`/`execute_document_delete`
      nuevas). `/new` invoca `discard_pending_for_chat`.
      **Excepción aprobada explícita (T4.7):** `analyze_document`/
      `DocumentService.ingest` siguen siendo automáticos — documentado en
      AGENTS.md §2.4 y `docs/governance.md`, no es un bypass sin registrar.
      **Pendiente para cerrar P0 del todo:** activar el flag en producción
      (hoy apagado — el bot sigue dependiendo de `confirm()` legacy vía LLM
      mientras tanto, por decisión explícita del propietario para no romper
      producción) y conectar `answerCallbackQuery` en el sender real de
      Telegram.
- [x] T7 · **Implementado (2026-10-02).** Unit/integration tests de replay,
      carrera, múltiples propuestas, cross-user/bot/chat, expiración,
      rollback y fallo ambiguo: 17 tests de integración en
      `tests/integration/test_proposal_consent.py` (ciclo completo, un solo
      uso, carrera real entre dos sesiones con un solo ganador, 6 rechazos
      parametrizados, `/new`, fallo ambiguo terminal, CHECK de estados) + 2
      de migración + 5 unitarios de modelo + 8 tests parametrizados
      (`TestExecuteWithoutAConfirmedProposal`) que cubren todas las ramas
      WRITE existentes, incluida TODO. Fresh/upgrade/downgrade probados en
      los tests de migración. E2E con Telegram/infraestructura real sigue
      sin ejecutarse (requiere autorización operativa aparte).
- [ ] T8 · Primer segmento completado: procedencia/acotación de las lecturas de notas y
      documentos con unit tests. Pendiente: `analyze_document`, resto de tools,
      adjunto directo al Agent y fallback legado; ensayos multimodales reales
      cuando exista harness apropiado.
- [ ] T9 · Con BL-8, ejecutar corpus adversarial/benigno sintético sobre Agent
      gobernado, con tools sin I/O; benchmark offline de detectores opcionales.
      No registrar contenido en observabilidad ni añadir vendor sin evaluación.
      El corpus está ampliado, pero no se ha ejecutado contra el Agent.
