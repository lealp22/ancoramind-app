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
- [x] T4 parcial (2026-10-25) · `src/observability/phoenix_export.py`:
      `MaskedSpanExporter` (allowlist, máscara por esquema+patrón, fail-closed por
      span, fail-open en I/O), procedencia `ancora.capture.source` ∈
      {user_text, final_reply, proposal_args, call_metadata}, tools sólo
      `propose_*`/`present_reply`, `build_phoenix_tracing`/`configure_`/`shutdown_`
      con provider propio no global, nunca lanza y sin dependencias nuevas
      (gRPC OTLP ya estaba). Tests en `tests/unit/test_phoenix_export.py`.
      Cableado con T6 (2026-10-25): `lifecycle.py` llama a `configure_phoenix_tracing`
      al crear el runner y a `shutdown_phoenix_tracing` en el apagado de
      observabilidad. Con flag OFF o config incompleta devuelve `None` y no crea nada.
      Pendiente de T4: máscara por esquema de campos de dominio concretos (T2) y
      prueba contra Phoenix real en Railway. El prototipo del spike sigue siendo
      sólo referencia.
- [x] T5 parcial (2026-10-23) · Settings `PHOENIX_*` en `src/config.py` y `.env.example`;
      `phoenix_tracing_active` exige flag + endpoint http(s) + API key + clave de
      seudónimo ≥32 + proyecto; configuración incompleta no impide arrancar
      (fail-open) y solo informa nombres, nunca valores. Pendiente: alta del
      provider (va con T4); aún sin efecto en producción.
- [x] T6 (2026-10-25, local, flag OFF) · Captura manual en
      `GovernedInteractionRunner.run` vía `src/observability/phoenix_capture.py`
      (política) + `phoenix_export.py` (exporter). Procedencia decidida por el
      llamador: el processor pasa `capture_user_text` (False para voz, adjunto sin
      texto sintetizado y cualquier otro llamador). Metadatos siempre (también en
      fallo, con sólo el nombre de la clase de error). Respuesta del modelo y
      argumentos `propose_*` sólo si el turno no tuvo adjuntos y todas sus tools
      están en `SAFE_READ_TOOLS`/`propose_*`/`present_reply`: una tool nueva queda
      excluida por defecto. Argumentos de tools de lectura nunca se capturan.
      Trazas nuevas (contexto vacío), una por turno, con `correlation_id`,
      `interaction_id` y seudónimo HMAC. Tests: `test_phoenix_capture.py` y
      procedencia en `test_interaction_processor.py`; 4 mutaciones de las reglas de
      privacidad rompen sus tests. **Desviación de la spec:** la spec capturaba la
      respuesta final siempre; aquí se omite tras leer/analizar documentos o con
      adjuntos, porque puede reproducir su contenido (ADR-007). Propietario
      confirma la excepción y `SAFE_READ_TOOLS` (2026-10-25); recogida en la spec,
      sección «Diseño de captura». `search_documents` queda dentro de la exclusión.
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
