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

- Validar el comportamiento real de los modelos y la ruta multimodal del
  Agent principal con un harness aislado; las unit tests prueban contratos
  de serialización, no inmunidad semántica a prompt injection.
- P0: autorización determinista de todas las mutaciones mediante prueba de
  consentimiento; requiere diseño de estados y pruebas de DB/Telegram.
- No se han realizado E2E ni cambios operativos/remotos.