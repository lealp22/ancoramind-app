# Tasks: 012 — FastAPI Lifespan for Reminder Worker

## T1: Especificación

- [x] Documentar la incompatibilidad de `add_event_handler` y el patrón
      lifecycle requerido.
- [x] Definir composición con el lifespan preexistente de AgentOS.

## T2: Infraestructura lifecycle

- [x] Crear helper en `src/agent/` que instale el wrapper de lifespan.
- [x] Mantener los tres auto-gates y logs actuales.
- [x] Crear task `reminder-worker` al entrar y cancelarla/esperarla al salir.
- [x] Guardar y limpiar la task en `app.state`.

## T3: Wiring de aplicación

- [x] Reemplazar `_register_reminder_worker()` en `src/main.py` por delegación
      al helper.
- [x] Eliminar `add_event_handler` y el global `_WORKER_TASK`.

## T4: Tests

- [x] Test de auto-gates (no se instala wrapper).
- [x] Test de inicio/cancelación/limpieza de task.
- [x] Test de composición y orden con lifespan existente.
- [x] Smoke test de import/build de main sin `AttributeError` con worker
      habilitado y deshabilitado (no se automatiza: el import construye AgentOS
      y puede emitir telemetría de red).

## T5: Verificación y documentación

- [x] Ejecutar unit tests, Ruff y mypy del alcance.
- [x] Crear `verification.md`.
- [x] Marcar BL-22 como hecho en BACKLOG.md y añadirlo a su registro.