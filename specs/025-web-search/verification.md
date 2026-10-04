# Verification: 025 — Búsqueda web gobernada

> Fecha: 2026-10-04

## Automatizada

- [x] `python -m pytest tests/unit/test_web_search_service.py
  tests/unit/test_tavily_web_search.py tests/unit/test_web_search_tools.py
  tests/unit/test_web_search_wiring.py tests/unit/test_config.py -q` →
  **32 passed**.
- [x] `ruff check src/ tests/ scripts/ migrations/` → limpio.
- [x] `mypy src/` → limpio (**122 source files**).
- [x] `pip install -e ".[dev]"` reparó el `.venv` que no tenía la dependencia
  ya declarada `pymupdf4llm`; `python -m pytest tests/unit/ -q` →
  **739 passed**.

## Manual pendiente

- [ ] En un entorno no productivo, fijar `WEB_SEARCH_ENABLED=true` y una
  `TAVILY_API_KEY` de prueba, iniciar la app y solicitar una búsqueda pública
  actual. Confirmar 3–5 fuentes, URLs visibles/citadas y que no aparece la
  consulta/snippets en logs o telemetría.
- [ ] Confirmar que un email/teléfono en la consulta se rechaza localmente y
  que un timeout/error de Tavily devuelve el mensaje controlado.