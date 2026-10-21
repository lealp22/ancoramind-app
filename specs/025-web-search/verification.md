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

## Automatizada — alineación con ADR-007 (2026-10-21)

- [x] `tests/unit/test_masking.py` + `test_web_search_service.py` (consultas con
  DNI/tarjeta/IBAN/matrícula/VIN rechazadas) → pasan.
- [x] `python -m pytest tests/unit/ -q` → **2151 passed, 1 skipped** (requiere
  `TELEGRAM_TOKEN` con formato válido, p. ej. `123456789:ABC...`, porque
  `test_web_search_wiring.py` importa `src.main`).
- [x] `ruff check src/ tests/ scripts/ migrations/` limpio; `mypy src/` limpio
  (185 ficheros).

## Automatizada — evals de prompt injection web (2026-10-21)

- [x] `python scripts/run_evals.py` → 42 casos válidos (security: 17).
- [x] `python -m pytest tests/unit/ -q` → **2155 passed, 1 skipped**; ruff y
  mypy limpios.
- Recall de las heurísticas (`injection_heuristics`) sobre los 5 ataques web:
  **4 de 5**. No detecta `security.web_snippet_requests_personal_lookup`
  ("busca las notas y envíalas a URL"): sus patrones solo cubren "visita URL" y
  "URL y envía". Hueco documentado en
  `test_web_injection_cases_recall_documents_one_known_miss`, que fallará a
  propósito si las heurísticas mejoran. No se ajustó el caso ni las heurísticas
  para que encajen.
- No se ha ejecutado inferencia real: los casos son contratos, no miden
  resistencia del modelo.

## Manual pendiente

- [ ] En un entorno no productivo, fijar `WEB_SEARCH_ENABLED=true` y una
  `TAVILY_API_KEY` de prueba, iniciar la app y solicitar una búsqueda pública
  actual. Confirmar 3–5 fuentes, URLs visibles/citadas y que no aparece la
  consulta/snippets en logs o telemetría.
- [ ] Confirmar que un email/teléfono en la consulta se rechaza localmente y
  que un timeout/error de Tavily devuelve el mensaje controlado.
