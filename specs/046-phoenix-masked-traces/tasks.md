# Tareas — Spec 046

- [ ] T0 · Spike (`spike.md`): informe `spike-result.md` local disponible (2026-10-22),
      Q1–Q5/Q7/Q9 acotados, Q6/Q8 y seam de procedencia pendientes; no cierre pleno.
- [ ] T1 · Decisión del propietario: aceptar ADR-007 y la enmienda acotada del
      principio 11; confirmar retención (usuarios: todos los autorizados).
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
- [ ] T5 · Settings nuevos y alta condicionada del provider (flag, endpoint, clave, clave de seudónimo);
      sin endpoint, API key o clave de seudónimo no se activa.
- [ ] T6 · Instrumentación (Agno o spans manuales según spike) con
      `correlation_id`, `interaction_id` y seudónimo HMAC de usuario.
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
