# Tareas — Spec 043

- [x] T1 · Modelos Pydantic y servicio en `src/domain/finops/` (sin Agno/FastAPI),
      incluido el seudónimo HMAC de usuario y la validación de `days` (1–90).
- [x] T2 · `src/repositories/finops.py`: consultas agregadas con `text()` y bind
      params. Coste `COALESCE(actual_cost, estimated_cost, 0)`.
- [x] T3 · Tests unitarios del servicio (seudónimo estable y no reversible,
      límites de `days`, presupuesto `null`).
- [x] T4 · Tests de integración PostgreSQL: coste actual>estimado, aislamiento
      entre usuarios, exclusión de `rejected`/`ignored`, ventana vacía, paridad
      con `summarize_spend`.
- [x] T5 · Test de privacidad: ninguna consulta referencia `payload_ciphertext`,
      `payload`, `arguments_fingerprint`; respuestas sin IDs de Telegram/sesión.
- [x] T6 · Rutas `GET /admin/dashboard/api/finops` y `/quality` en
      `admin_dashboard.py` con auth existente; tests 401/422/404-si-desactivado.
- [x] T7 · Panel en `dashboard.html` (barras CSS, tablas, selector de ventana,
      `textContent`, sin recursos externos).
- [x] T8 · `EXPLAIN` de las consultas con 90 días sobre datos locales sintéticos.
- [ ] T9 · Documentar en `docs/development.md` y en el cuerpo del panel qué
      gasto no se incluye (Dream, voz sin evento).
- [ ] T10 · Gates: pytest unit + integration, Ruff, mypy, `git diff --check`.
