# Tareas — Spec 045

- [x] T1 · Tests rojos de impresión única: N criterios imprimen el bloque una vez,
      reanudar a medias una vez, etiquetas y orden sin cambios, fail/x detiene.
      `tests/unit/test_eval_review_ux.py`: 2 rojos (defecto) y 2 guardas verdes.
- [x] T2 · Renderer de secciones en `eval_campaign_runner.py` (formato legible,
      prefijo fijo por línea, escapado de controles/bidi/formato y saltos).
      Tests de inyección: valor que imita sección o `[p]/[f]/[x]`.
      `render_section` + 8 tests; aún no cableado a la consola (eso es T3).
- [x] T3 · `review_saved` y `TerminalCampaignReviewer`: un revisor por caso, con
      criterios pendientes seguidos. Mantener `save` por criterio y
      `pause_on_disconnect`.
      `criterion_offset` se sustituye por `criterion_indices` (índices absolutos).
- [x] T4 · Lista cerrada de `reason` en `eval_console.py` y mapeo de excepciones.
      Tests: cada motivo, `unexpected`, ausencia de texto de excepción y rutas.
      Motivos: `console_not_interactive`, `review_disconnected`,
      `evidence_unreadable_or_wrong_key`, `run_not_found`, `unexpected`.
- [x] T5 · `--human` en `status` y `session-status` con tabla fija de siguiente
      paso. Test: JSON sin `--human` idéntico; ningún paso sugiere `run`.
      `human_status`/`human_session` en `eval_console.py`; estados desconocidos
      → «Sin acción sugerida».
- [x] T6 · Comprobar que solo cambian ficheros de `_HARNESS` (test sobre
      `session_scope` antes/después) y documentar la nueva huella en el runbook.
      Scope idéntico entre `f4d8bd8` y el árbol actual; 2 tests; `runbook.md`.
- [ ] T7 · Gates: pytest unit + integration, Ruff, mypy, `git diff --check`.
      Sin commit, push, despliegue ni inferencia por el agente.
