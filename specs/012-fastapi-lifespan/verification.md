# Verification: 012 — FastAPI Lifespan for Reminder Worker

> **Fecha:** 2026-09-10 · **Entorno:** Windows 11 + Python 3.12 (venv)
> **Estado:** ✅ verificado

---

## Resultado

| Check | Resultado |
|---|---|
| Worker lifecycle unit tests | ✅ 3 passed: auto-gates, task start/cancel/cleanup, composición con lifecycle previo |
| Worker domain unit tests | ✅ 5 passed: ciclo, entrega, error y cancelación (specs/010) |
| `pytest tests/unit/ -q` | ✅ **171 passed** |
| `ruff check src/ tests/ scripts/` | ✅ limpio |
| `mypy src/agent/lifecycle.py src/main.py tests/unit/test_reminder_worker_lifecycle.py` | ✅ sin issues |
| `from src.main import app` con worker habilitado | ✅ `FastAPI` construido sin `AttributeError` |
| `from src.main import app` con worker deshabilitado | ✅ `FastAPI` construido; log de auto-gate correcto |
| `pytest tests/integration/ -q` | ⚠️ 24 skipped: PostgreSQL/Docker no disponible en este entorno; sin fallos |

## Qué se implementó

| Pieza | Fichero |
|---|---|
| Installer del lifecycle, auto-gates y wrapper de lifespan | `src/agent/lifecycle.py` |
| Delegación fina; retirada de handlers/global task | `src/main.py` |
| Tests aislados del lifecycle | `tests/unit/test_reminder_worker_lifecycle.py` |

## Comportamiento verificado

1. `install_reminder_worker_lifespan()` no reemplaza el lifecycle existente
   cuando falta cualquiera de los tres requisitos; conserva los logs de
   auto-gate.
2. Cuando los requisitos existen, entra primero al lifecycle original de
   AgentOS/Starlette, crea una sola task llamada `reminder-worker` y la expone
   como `app.state.reminder_worker_task`.
3. Al salir, cancela la task, espera su terminación suprimiendo únicamente
   `asyncio.CancelledError`, elimina el atributo de `app.state` y solo después
   sale del lifecycle original.
4. La causa de BL-22 queda eliminada: ya no hay llamadas a
   `app.add_event_handler(...)`.

## Smoke tests de importación

Se ejecutaron manualmente los dos comandos siguientes contra la configuración
local (la importación construye AgentOS y puede emitir telemetría, por eso no se
incluyeron como tests unitarios aislados):

```powershell
.venv/Scripts/python.exe -c "from src.main import app; print(type(app).__name__)"
$env:REMINDER_WORKER_ENABLED='false'
.venv/Scripts/python.exe -c "from src.main import app; print(type(app).__name__)"
```

Ambos construyeron `FastAPI`; el primero verificó que desapareció el
`AttributeError` original y el segundo registró `Reminder worker disabled`.

## Alcance no modificado

- La lógica del worker (`run_once`, `run_forever`), el notifier y las variables
  de configuración siguen siendo los de specs/010.
- No se ejecutó entrega real de Telegram: permanece pendiente de la validación
  E2E documentada en specs/010 y no depende de esta corrección de lifecycle.