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

## Manual — validación local sin Telegram (2026-10-21)

`python -m scripts.validate_web_search [--live]` ejercita la tool `search_web`
real y `WebSearchService`, no el Agent. Los rechazos usan un proveedor falso
(no llegan a Tavily); los errores usan una clave inválida (sin cobro); solo
`--live` gasta 1 crédito. Clave de `.env`, nunca impresa.

- [x] Rechazo local con mensaje controlado: DNI, tarjeta, email, teléfono,
  matrícula, IBAN, consulta vacía y de más de 300 caracteres. Cero llamadas al
  proveedor.
- [x] Errores controlados: HTTP 401, timeout/transporte y servicio sin
  configurar devuelven mensaje en español sin proveedor, código ni clave.
- [x] Búsqueda real ("¿Qué es la inflación?"): **5 fuentes**, todas `https`,
  origen `public_web`, fecha de consulta presente, envoltorio `untrusted_data`.
  Fuentes: Banco de España, Banxico, FocusEconomics, YouTube (Santander), INE
  Uruguay. Tavily informó **1 crédito**; la segunda consulta idéntica salió de
  la caché.
- [x] Privacidad en los logs capturados durante la ejecución: no aparecen la
  clave, las consultas ni los snippets.

**Límites de esta validación:** no cubre el flujo del Agent (cuándo decide
buscar, si cita las URLs, cómo sintetiza) ni la telemetría real de Grafana/OTel,
solo los logs de Python capturados en el proceso. Calidad de fuentes: una de
cinco es un vídeo y dos son de otros países, algo a tener en cuenta en el prompt.

## Manual pendiente

- [ ] Flujo del Agent por Telegram (Railway + Telegram Web con Playwright,
  sesión iniciada por el propietario): confirmar que el Agent decide buscar,
  cita las URLs y que no aparecen consulta/snippets en la telemetría. Bloqueado
  por el incidente de Railway; las variables ya están puestas, falta que el
  deployment pendiente (`NEEDS_APPROVAL`) se despliegue y verificar su SHA.
