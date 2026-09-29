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

## Próximos incrementos: no realizados

- [ ] T6 · Diseñar e implementar consentimiento tipado en Core, vinculado a
      evento autenticado posterior y propuesta específica; acordar UX/TTL y
      semántica de fallo antes de tocar DB o canal. Mismo guard para **todos**
      los `execute_*`, sin bypass vía tool directa. Revisar `remember_note` y
      altas documentales automáticas según la política de gobernanza.
- [ ] T7 · Unit/integration tests de replay, carrera, múltiples propuestas,
      cross-user, expiración, rollback y fallo ambiguo; E2E solo con
      infraestructura y autorización operativa.
- [ ] T8 · Provenance/acotación de notas y resultados de tools, adjunto directo
      al Agent y fallback legado; incluir ataques multimodales cuando haya
      harness apropiado.
- [ ] T9 · Con BL-8, ejecutar corpus adversarial/benigno sintético sobre Agent
      gobernado, con tools sin I/O; benchmark offline de detectores opcionales.
      No registrar contenido en observabilidad ni añadir vendor sin evaluación.