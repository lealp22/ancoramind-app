# Tareas — Spec 046

- [ ] T0 · Spike (`spike.md`): informe `spike-result.md` local disponible (2026-10-22),
      Q1–Q5/Q7/Q9 acotados, Q6/Q8 y seam de procedencia pendientes; no cierre pleno.
- [x] T1 · Decisión del propietario (2026-10-23): ADR-007 Accepted con la enmienda
      acotada del principio 11, captura manual, retención 30 días, todos los
      usuarios autorizados. Autoriza implementar con flag OFF; no la activación.
- [ ] T2 parcial · `src/observability/masking.py` ya existente: detectores por patrón;
      esquema sólo en exporter experimental, aún no en captura productiva.
      Alcance previsto: detectores por esquema, patrón con
      validación (Luhn, DNI/NIE, IBAN, matrícula, VIN, email, teléfono, tokens) y
      red de seguridad numérica.
- [x] T3 · Corpus existente válido/inválido y 10 controles cotidianos en español;
      0 positivos en esos controles, no medida poblacional de falsos positivos.
- [ ] T4 · `phoenix_export.py`: exporter envolvente con allowlist, máscara y
      fail-closed por span. Prototipo sintético en `scripts/phoenix_spike/exporter.py`,
      sin integración en `src/`; no confundir con exporter de producción terminado.
- [x] T5 parcial (2026-10-23) · Settings `PHOENIX_*` en `src/config.py` y `.env.example`;
      `phoenix_tracing_active` exige flag + endpoint http(s) + API key + clave de
      seudónimo ≥32 + proyecto; configuración incompleta no impide arrancar
      (fail-open) y solo informa nombres, nunca valores. Pendiente: alta del
      provider (va con T4); aún sin efecto en producción.
- [ ] T6 · Captura manual en `GovernedInteractionRunner.run` (no en `ainvoke` ni
      auto-instrumentación) según «Diseño de captura» de la spec: allowlist por
      procedencia, voz excluida, exclusión previa de adjuntos/lecturas/historial y
      rutas de extracción/Dream/compactación/evals, `correlation_id`,
      `interaction_id` y seudónimo HMAC. Diseño aprobado 2026-10-23.
- [ ] T7 · Test de privacidad: canarios no llegan al exporter; Grafana sin contenido;
      audio/adjuntos/documentos ausentes; LLM y BD intactos.
- [ ] T8 · Test fail-open: Phoenix caído o error de máscara no afecta al Agent.
- [ ] T9 · Documentar en `docs/production-security-privacy.md` (inventario, retención,
      DPIA, borrado por usuario), actualizar los términos del piloto (texto de
      todos los usuarios autorizados, enmascarado, 30 días) y enmendar
      AGENTS.md/ADR-006.
- [ ] T10 · Runbook: variables en Railway, red privada, retirada del dominio público.
- [ ] T11 · Gates: pytest unit + integration, Ruff, mypy, `git diff --check`; SHA/CI.
- [ ] T12 · Activación controlada: flag ON solo para el propietario y verificación E2E.
