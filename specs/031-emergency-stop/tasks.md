# Tasks — specs/031 / BL-44

## T1 — Dominio puro ✅ — 2026-10-10

- [x] `src/domain/emergency_stop/models.py`: `EmergencyStopState`,
      `EmergencyStopActiveError`.
- [x] `src/domain/emergency_stop/ports.py`: `EmergencyStopReader` (Protocol,
      síncrono, cero I/O).
- [x] `src/domain/emergency_stop/service.py`: `EmergencyStopManager`
      (en memoria, bootstrap inactivo, `activate`/`deactivate` con
      actor/reason obligatorios).
- [x] Tests: `tests/unit/test_emergency_stop_service.py` (bootstrap inactivo,
      activar, desactivar con auditoría, actor/reason en blanco rechazados).
- **Listo cuando:** Ruff/mypy limpios, sin dependencias de infraestructura. ✅

## T2 — Wiring en el camino de inferencia ✅ — 2026-10-10

- [x] `GovernedModelMixin`/`build_governed_model`
      (`src/agent/governed_model.py`): nuevo `_governed_stop_reader`,
      comprobado antes de `reserve_model_call`; emite
      `ancora.emergency_stop.blocked`.
- [x] `AgnoLLMAccess` (`src/agent/llm_access.py`): nuevo `stop_reader`
      opcional, propagado a `build_governed_model`.
- [x] `GovernedInteractionRunner` (`src/agent/governed_interaction_runner.py`):
      nuevo `stop_reader` opcional, comprobado en
      `prepare_execution_context` antes de construir el `ExecutionContext`.
- [x] `InteractionProcessor` (`src/domain/interactions/processor.py`): nuevo
      `except EmergencyStopActiveError` → `FAILED_CONTROLLED`.
- [x] Tests: `test_governed_model.py` (3 nuevos: bloquea sin reservar budget
      ni llamar al proveedor, no bloquea inactivo, no bloquea sin reader),
      `test_governed_interaction_runner.py` (2 nuevos: bloquea antes de
      crear el Agent, no bloquea inactivo),
      `test_interaction_processor.py` (1 nuevo:
      `EmergencyStopActiveError` → `FAILED_CONTROLLED`, nunca reintentado).
- **Listo cuando:** tests existentes de los tres ficheros siguen en verde sin
  cambios de comportamiento no relacionados; Ruff/mypy limpios. ✅

## T3 — API admin HTTP + CLI ✅ — 2026-10-10

- [x] `src/agent/emergency_stop_admin.py::install_emergency_stop_admin_api`
      — reutiliza el gate de `runtime_config_admin.py`
      (`RUNTIME_CONFIG_ADMIN_ENABLED`/`RUNTIME_CONFIG_ADMIN_TOKEN`), sin
      secreto nuevo. `GET /status`, `POST /activate`, `POST /deactivate`.
- [x] `scripts/emergency_stop.py` — mismo esqueleto que
      `scripts/runtime_config.py` (`status`/`activate`/`deactivate`).
- [x] Wiring en `src/main.py`/`src/agent/lifecycle.py`:
      `EmergencyStopManager()` construido una vez en `create_app()`,
      inyectado en `AgnoLLMAccess`/`GovernedInteractionRunner` y en
      `install_emergency_stop_admin_api` bajo el mismo flag de admin.
- [x] Tests: `tests/unit/test_emergency_stop_admin.py` (7: no instalado si
      el admin está apagado, 401 sin token válido, round-trip
      activar→status→desactivar, 422 actor en blanco, 422 reason en blanco).
- **Listo cuando:** la respuesta nunca expone el token; `pytest`, `ruff`,
  `mypy` limpios. ✅

## T4 — Documentación y cierre ✅ — 2026-10-10

- [x] `BACKLOG.md` BL-44: marcado como implementado localmente con fecha,
      referencia a `specs/031`, limitaciones conocidas (§8 de spec.md:
      sin persistencia durable, extracción de documentos no cubierta, panel
      de dashboard diferido, sin broadcast multi-instancia).
- [x] Housekeeping de persistencia Postgres registrado como pendiente
      separado (mismo patrón que BL-13/Dream T1).
- **Listo cuando:** no quedan afirmaciones "pendiente de diseño" en
  BACKLOG.md sobre lo que este incremento sí entrega (dominio + wiring +
  API + CLI); la persistencia durable sigue correctamente marcada como no
  implementada. 1104 unit tests, Ruff y `mypy src/` (159 ficheros) limpios. ✅
