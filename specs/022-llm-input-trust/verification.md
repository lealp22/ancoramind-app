# Verificación — Spec 022 / BL-39

> Estado: verificación local parcial; sin infraestructura externa.

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
- P0: autorización determinista de todas las mutaciones mediante prueba de
  consentimiento; el diseño de estados existe, pero faltan implementación y
  pruebas de DB/Telegram.
- No se han realizado E2E ni cambios operativos/remotos.