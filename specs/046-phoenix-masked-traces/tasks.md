# Tareas — Spec 046

- [ ] T0 · Spike (`spike.md`): responder Q1–Q9 y escribir `spike-result.md`.
- [ ] T1 · Decisión del propietario: aceptar ADR-007 y la enmienda acotada del
      principio 11; confirmar retención (usuarios: todos los autorizados).
- [ ] T2 · `src/observability/masking.py`: detectores por esquema, patrón con
      validación (Luhn, DNI/NIE, IBAN, matrícula, VIN, email, teléfono, tokens) y
      red de seguridad numérica.
- [ ] T3 · Corpus sintético válido/inválido + tests de detectores y de falsos
      positivos sobre texto cotidiano en español.
- [ ] T4 · `phoenix_export.py`: exporter envolvente con allowlist, máscara y
      fail-closed por span.
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
