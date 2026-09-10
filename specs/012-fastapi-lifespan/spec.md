# Spec: 012 — FastAPI Lifespan for Reminder Worker

> **Backlog:** BL-22
> **Status:** implemented (2026-09-10)
> **Target:** sustituir el wiring obsoleto de startup/shutdown del reminder
> worker por FastAPI/Starlette lifespan, sin cambiar el comportamiento del
> worker definido en specs/010.

---

## Requirement

El runtime instalado ya no expone `FastAPI.add_event_handler(...)`. Por ello,
al construir `src.main` con el reminder worker habilitado se produce un
`AttributeError` antes de poder arrancar la aplicación. El worker de specs/010
debe seguir arrancando dentro del mismo proceso, pero su ciclo de vida debe
usar el patrón actual de FastAPI: `lifespan` con `@asynccontextmanager`.

### Must Have

- Eliminar el uso de `app.add_event_handler("startup", ...)` y
  `app.add_event_handler("shutdown", ...)` para el reminder worker.
- Conservar los auto-gates y sus mensajes: `REMINDER_WORKER_ENABLED`,
  `ANCORA_DATABASE_URL` y `TELEGRAM_TOKEN`.
- Con los requisitos presentes, crear un único `asyncio.Task` nombrado
  `reminder-worker` al entrar en el lifespan; al salir, cancelarlo, esperar su
  finalización suprimiendo solo `asyncio.CancelledError` y limpiar la referencia.
- Preservar el lifespan que AgentOS/Starlette ya hubiera configurado en la app:
  el wrapper debe entrar en él antes de iniciar el worker y salir de él después
  de detenerlo.
- Mantener el dominio independiente de FastAPI/Agno: lifecycle y wiring solo
  pueden vivir en `src/agent/`/`src/main.py`.
- Tests unitarios del wiring: auto-gates, arranque, cancelación limpia y
  composición con un lifespan previo.

### Should Have

- Guardar la task en `app.state.reminder_worker_task`, no en un global de
  módulo, para evitar interferencia entre instancias de app/reload/tests.
- El helper de infraestructura devuelve si instaló el lifecycle (`bool`) para
  hacer los tests explícitos.

### Won't Have

- Cambiar la lógica `run_once()` / `run_forever()` ni el notifier (specs/010).
- Introducir un proceso o servicio Railway separado.
- Cambiar variables de entorno, intervalo o política de reintento.
- Modificar specs/010: es registro histórico de su implementación.

---

## Design

```text
AgentOS.get_app() → FastAPI app con lifespan existente (si lo hubiera)
       │
       └─ install_reminder_worker_lifespan(app, settings)
             ├─ auto-gates fallan → log + no cambia lifespan
             └─ auto-gates pasan → envuelve app.router.lifespan_context
                    │
                    ├─ async with lifespan original
                    │     ├─ create_task(RemindersWorker.run_forever(...))
                    │     ├─ yield → app atiende tráfico
                    │     └─ finally: cancel task + await + limpiar app.state
                    └─ sale lifespan original
```

`main.py::_register_reminder_worker()` queda como adaptador fino que delega en
el helper de infraestructura. Esto permite probar la composición sin importar
el módulo `src.main`, que construye la app global al importarse.

La documentación oficial de FastAPI recomienda `lifespan` para startup y
shutdown relacionados, e indica que no se mezclan handlers de eventos con un
lifespan configurado.

## Success Criteria

1. Con worker habilitado y credenciales/BD configuradas, importar `src.main`
   no lanza `AttributeError` por `add_event_handler`.
2. Durante lifespan el worker se inicia una vez; al cerrar, recibe cancelación,
   se espera su tarea y `app.state.reminder_worker_task` se limpia.
3. Con cada auto-gate fallido no se crea task ni se reemplaza el lifespan base;
   se conserva el log informativo equivalente.
4. Un lifespan preexistente se ejecuta en orden correcto: entrada original →
   worker → detención worker → salida original.
5. `pytest tests/unit/`, Ruff y mypy de los archivos nuevos/modificados pasan.