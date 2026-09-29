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

## Pendiente

- Validar el comportamiento real de los modelos y la ruta multimodal del
  Agent principal con un harness aislado; las unit tests prueban contratos
  de serialización, no inmunidad semántica a prompt injection.
- P0: autorización determinista de todas las mutaciones mediante prueba de
  consentimiento; requiere diseño de estados y pruebas de DB/Telegram.
- No se han realizado E2E ni cambios operativos/remotos.