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
- [ ] T6b · Migrar schema, procedencia y transacciones; imponer en Core el
      mismo guard y claim para **todos** los `execute_*`, notes e ingesta
      documental, sin bypass vía tool o AgentOS legado; validar presentación
      real y consentimiento previo al Agent. Sin excepción WRITE aprobada.
- [ ] T7 · Unit/integration tests de replay, carrera, múltiples propuestas,
      cross-user/bot/chat, expiración, rollback y fallo ambiguo; pruebas de
      todas las ramas WRITE, fresh/upgrade/downgrade; E2E solo con
      infraestructura y autorización operativa.
- [ ] T8 · Primer segmento completado: procedencia/acotación de las lecturas de notas y
      documentos con unit tests. Pendiente: `analyze_document`, resto de tools,
      adjunto directo al Agent y fallback legado; ensayos multimodales reales
      cuando exista harness apropiado.
- [ ] T9 · Con BL-8, ejecutar corpus adversarial/benigno sintético sobre Agent
      gobernado, con tools sin I/O; benchmark offline de detectores opcionales.
      No registrar contenido en observabilidad ni añadir vendor sin evaluación.
      El corpus está ampliado, pero no se ha ejecutado contra el Agent.