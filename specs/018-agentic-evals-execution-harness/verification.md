# Verification: 018 — Isolated Agentic Evals Execution Harness

> **Fecha:** 2026-09-27 (T1–T5) / 2026-10-03 (T6) · **Estado:** ✅ T1–T6
> verificados localmente, sin inferencia real; T7 (ejecución LLM real) y T8
> (scoring semántico) permanecen pendientes y requieren credenciales/
> presupuesto/etiquetado humano aprobados aparte.

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
- `pytest tests/unit/ -q` → 506 passed.
- `pytest tests/integration/ -q` → 71 passed.
- `mypy src/agent/evals.py` → sin issues.
- `ruff check src/ tests/ scripts/ migrations/` y `git diff --check` → passed.

## Incremento T6 — 2026-10-03

Adaptador físico implementado: `src/agent/eval_physical_executor.py`
(`GovernedPhysicalEvalExecutor`) construye un `Agent` real por caso — modelo
resuelto vía `LLMAccess` inyectado (nunca un provider directo), snapshot
(`bootstrap_runtime_configuration()`, revisión 0, sin PostgreSQL) y budget
propios y aislados de producción, mismo `tool_hooks`/`tool_call_limit`/
`retries=0`/`telemetry=False` que la composición de producción pero sin
`GovernedAgentFactory` (ese factory fija `add_history_to_context=True` y una
sesión de BD reales, ajenas a un caso sintético de un solo turno). Catálogo de
tools simuladas en `src/agent/eval_tools.py` (las 15 referenciadas por los
catálogos actuales), sin importar `src.repositories`/`src.storage`/tools de
producción, con un `SyntheticProposalStore` en memoria por caso.

`EvalCase.synthetic_context` se simula sin que el propio texto otorgue
autoridad: una propuesta pendiente (`pending_proposal`) se siembra en el
store (código, no el modelo) y se expone al modelo como un turno previo
(`agno.models.message.Message`) — igual que vería un usuario real su propio
historial de Telegram — y es el store, no la palabra del modelo, quien decide
si `execute_*` tiene algo real que confirmar. Un adjunto nuevo
(`attachment` sin `analysis_completed`) se simula con un `File` con bytes
inertes para que `analyze_document` sea invocable. El resto de claves de
contexto (`untrusted_note`, `untrusted_document_excerpt`/`_summary`,
`untrusted_filename`, `vehicle_matches`, `resolved_vehicle`) se inyectan en el
propio texto de retorno de la tool simulada correspondiente, reutilizando
`src/agent/tools/untrusted_results.py` (helper puro, sin I/O) — así los casos
de `security` ejercen una resistencia real a instrucciones embebidas en el
resultado de una tool, no una comprobación vacía.

`outcome`/`requires_user_confirmation` se derivan solo de hechos observables
en `RunOutput.tools` (nombres de tool realmente invocados), nunca del texto de
respuesta: `execute_*` observado → `confirm_pending_action`; cualquier otra
tool → `tool_call`; ninguna → el sentinel `no_tool_call`, deliberadamente
distinto de `clarify`/`safe_response` del catálogo — distinguir esos dos
exige juzgar el texto semánticamente, que es T8 (Jev u otro juez), no T6.
Casos que esperan `clarify`/`safe_response` no igualan por `outcome` con este
adaptador; es una limitación de alcance documentada, no un fallo.

Validado con un `Model` scripted en memoria (mismo patrón que
`_ScriptedToolModel` de `tests/unit/test_tool_budget_hooks.py`), sin red ni
coste: `tests/unit/test_eval_tools.py` (8 tests, catálogo simulado + store) y
`tests/unit/test_eval_physical_executor.py` (4 tests: tool_call,
propose_*→confirmación requerida, pending_proposal→confirm_pending_action,
sentinel no_tool_call).

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/test_eval_tools.py tests/unit/test_eval_physical_executor.py -q
.venv\Scripts\python.exe -m pytest tests/unit/ -q
.venv\Scripts\python.exe -m ruff check src/ tests/ scripts/ migrations/
.venv\Scripts\python.exe -m mypy src/
```

- `pytest tests/unit/test_eval_tools.py tests/unit/test_eval_physical_executor.py -q` → 12 passed.
- `pytest tests/unit/ -q` → 705 passed.
- `pytest tests/integration/ -q` → no ejecutado (sin PostgreSQL/Docker en este
  incremento; ninguno de los módulos nuevos toca persistencia).
- `ruff check` y `mypy src/` → limpios (116 módulos).

## Límite pendiente

**Actualización 2026-10-11 (BL-39/40):** el catálogo simulado y el Agent de eval
ya no exponen `execute_*`; `SyntheticProposalStore.confirm` rechaza sin consumir.
El adaptador rechaza `expected_outcome=confirm_pending_action` y `required_tool`
`execute_*` antes de resolver el modelo (test verifica cero llamadas). No son
casos aprobados ni confirmación ejecutada: el catálogo histórico JSON continúa
estáticamente válido, pero esas dos evaluaciones deben trasladarse a un harness
determinista del Core y actualizar sus expectativas antes de ejecutar T7.
Otros casos se ejecutan con reads/proposals y el mismo framing de datos.
Unit scripted sin red/coste; 1263 unit passing en la suite final.

Ningún test de este incremento llama a un provider real, a `AgnoLLMAccess`
con credenciales, ni a `scripts/run_evals.py` (sin cambios). T7 (ejecutar la
modalidad LLM real con credenciales/presupuesto aprobados, fuera de CI por
defecto) y T8 (scoring semántico opcional con etiquetas humanas) permanecen
pendientes y bloqueados por decisiones del propietario, no por este código.
