# Verification: 018 — Isolated Agentic Evals Execution Harness

> **Fecha:** 2026-09-27 · **Estado:** ✅ T1–T5 verificados localmente; el
> adaptador físico y cualquier inferencia real permanecen pendientes.

## Alcance

- Harness aislado sin providers, LLMAccess, base de datos, Telegram ni tools de
  producción.
- Checks deterministas y reporte metadata-only en memoria.
- El executor de tests es un fake; ninguna inferencia ni llamada externa forma
  parte de esta validación.

## Evidencia local

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/test_eval_catalog.py tests/unit/test_governed_evals.py -q
.venv\Scripts\python.exe -m pytest tests/unit/ -q
.venv\Scripts\python.exe -m ruff check src/ tests/ scripts/ migrations/
.venv\Scripts\python.exe -m mypy src/agent/evals.py
git diff --check
```

- `python scripts/run_evals.py` → 19 casos válidos en seis categorías.
- `pytest tests/unit/test_eval_catalog.py tests/unit/test_governed_evals.py -q`
  → 11 passed.
- `pytest tests/unit/ -q` → 497 passed.
- `pytest tests/integration/ -q` → 71 passed.
- `mypy src/agent/evals.py` → sin issues.
- `ruff check src/ tests/ scripts/ migrations/` y `git diff --check` → passed.

## Límite pendiente

El siguiente adaptador físico no se implementa aquí. Debe pasar por `LLMAccess`
y Gateway, capturar un snapshot/budget específicos de evaluación y usar sólo
tools simuladas. Su ejecución requiere credenciales, presupuesto y autorización
explícitos; no habilitarlo por defecto en CI.