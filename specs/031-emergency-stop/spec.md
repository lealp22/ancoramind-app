# specs/031 — Parada de emergencia manual para Agent/LLM (BL-44)

> **Status:** implementado localmente (dominio + wiring + API admin + CLI);
> persistencia durable diferida — ver §8.

## 1. Problema

El único freno de gasto hoy es el hard-stop **automático** al 90% del gasto
(`CostGovernanceConfig.hard_stop_threshold_pct`, evaluado una vez por run en
`GovernedInteractionRunner.prepare_execution_context`). No existe nada que el
propietario pueda accionar **a mano** si el servicio falla de forma general o
el gasto se dispara por una vía no cubierta por ese umbral — por ejemplo, un
bucle de tool calls caro dentro de un run ya en marcha. Surgió al diseñar
BL-43, que deliberadamente lo dejó fuera de alcance por tocar la ruta crítica
de `LLMAccess`/`GovernedModel`.

## 2. Alcance de este incremento

Backend completo (dominio + wiring + API admin HTTP + CLI), con cobertura de
tests, sin tocar Postgres/Docker (sin disponibilidad de infraestructura en
esta sesión). El toggle visual en `/admin/dashboard` (BL-43) queda diferido
explícitamente — no se construye aquí (decisión confirmada con el
propietario, ver §8).

### No-objetivos (explícitos)

- No sustituye el hard-stop automático de gasto (BL-23/specs/013 T12): son
  complementarios. El automático actúa por umbral de gasto; este es un
  interruptor manual, para cualquier motivo.
- No persiste el estado en Postgres en este incremento (§8) — el contrato
  (`EmergencyStopReader`) sí deja espacio para una implementación durable
  futura sin tocar los puntos de llamada.
- No añade un panel al dashboard de BL-43 — API HTTP + CLI son suficientes
  para operar manualmente; el panel visual es un seguimiento explícito.
- No reemplaza `RuntimeConfigManager`/el ciclo publish→activate de
  specs/013: es una señal independiente y deliberadamente más simple
  (activar/desactivar inmediato, sin revisiones ni checksum) porque una
  parada de emergencia no puede esperar esa ceremonia.

## 3. Dos puntos de comprobación

- **Nivel de run** — `GovernedInteractionRunner.prepare_execution_context()`
  (`src/agent/governed_interaction_runner.py`): comprobación barata antes de
  construir el `ExecutionContext`, misma posición que
  `evaluate_cost_governance`. Evita arrancar un Agent entero si ya se sabe
  que está parado.
- **Nivel de llamada** — dentro de `GovernedModelMixin.ainvoke`
  (`src/agent/governed_model.py`), primera comprobación, antes de
  `context.budget.reserve_model_call(...)`. Es el único punto que
  intercepta **cada** llamada física al Gateway (`aresponse` ya lo envuelve
  — specs/013 T7), así que es el que de verdad cumple "antes de cada llamada
  al Gateway": puede interrumpir un run ya en marcha que esté en un bucle de
  tool calls, que el chequeo de nivel-run no cubre.

Ambos leen el mismo lector síncrono (`EmergencyStopReader.current()`), cero
I/O añadido al camino de inferencia.

## 4. Dominio — `src/domain/emergency_stop/`

- `models.py`: `EmergencyStopState` (`active`, `reason`, `activated_by`,
  `activated_at`) y `EmergencyStopActiveError(RuntimeError)` — `reason` es
  texto libre del operador: puede aparecer en logs/respuesta HTTP admin,
  nunca en atributos de telemetría (misma disciplina que
  `CostGovernanceError`).
- `ports.py`: `EmergencyStopReader` (`Protocol`, un solo método síncrono
  `current()`, cero I/O).
- `service.py`: `EmergencyStopManager` — mismo rol que `RuntimeConfigManager`
  pero sin backend DB en este incremento: `activate(*, actor, reason)` /
  `deactivate(*, actor, reason)` mutan el estado cacheado in-process;
  `current()` implementa `EmergencyStopReader`. Bootstrap: `active=False`.

## 5. Wiring

- `GovernedModelMixin`/`build_governed_model` (`src/agent/governed_model.py`):
  nuevo `_governed_stop_reader`; `ainvoke` lanza `EmergencyStopActiveError`
  (y emite `ancora.emergency_stop.blocked`) sin reservar budget ni llamar al
  proveedor cuando el reader reporta activo.
- `AgnoLLMAccess` (`src/agent/llm_access.py`): nuevo `stop_reader` opcional en
  el constructor, propagado a `build_governed_model`.
- `GovernedInteractionRunner` (`src/agent/governed_interaction_runner.py`):
  nuevo `stop_reader` opcional; comprobado en `prepare_execution_context`
  antes de construir el `ExecutionContext`.
- `InteractionProcessor` (`src/domain/interactions/processor.py`): nuevo
  `except EmergencyStopActiveError` junto a `CostGovernanceError`, mismo
  tratamiento — `FAILED_CONTROLLED`, nunca se reintenta.
- `src/agent/lifecycle.py`/`src/main.py`: `EmergencyStopManager()` se
  construye una vez en `create_app()` y se inyecta en `AgnoLLMAccess` y
  `GovernedInteractionRunner` dentro de `install_interaction_processor_lifespan`.

## 6. API admin HTTP — `src/agent/emergency_stop_admin.py`

Reutiliza el mismo gate que `runtime_config_admin.py`
(`RUNTIME_CONFIG_ADMIN_ENABLED`/`RUNTIME_CONFIG_ADMIN_TOKEN`) en vez de un
secreto nuevo — misma superficie de control-plane protegida, otro manager:

- `GET /admin/emergency-stop/status`
- `POST /admin/emergency-stop/activate` (`{reason}` + header
  `X-Ancora-Admin-Actor`)
- `POST /admin/emergency-stop/deactivate` (mismo contrato)

Instalado en `main.py` junto a `install_runtime_config_admin_api`, bajo el
mismo `if settings.runtime_config_admin_enabled:` — sin flag nuevo.

## 7. CLI — `scripts/emergency_stop.py`

Mismo esqueleto que `scripts/runtime_config.py`: `status`,
`activate --reason "..."`, `deactivate --reason "..."`, bearer token desde
entorno, nunca logeado.

## 8. Limitaciones conocidas, aceptadas para este incremento

- **Solo en memoria, sin persistencia durable** — sin Postgres/Docker
  disponibles en esta sesión. Un restart del proceso borra la parada y
  vuelve a `active=False`; si el problema que motivó la parada persiste, el
  operador debe volver a activarla. La tabla Postgres
  (`ancora.emergency_stop_state`) + repositorio real detrás del mismo
  `EmergencyStopReader` quedan como siguiente incremento explícito — mismo
  patrón que BL-13/Dream (dominio + wiring completos, persistencia diferida).
- **No cubre la ruta de extracción de documentos** —
  `src/agent/tools/documents.py::_get_document_service()` construye sus
  propias instancias de `AgnoLLMAccess` (extracción + embeddings) sin acceso
  al `EmergencyStopManager` singleton de `main.py`: esas llamadas de
  inferencia no se detienen con este interruptor. Requeriría un acceso
  compartido al manager (p. ej. vía `Settings`/un localizador de servicio) —
  fuera de alcance aquí, documentado como brecha conocida.
- **Panel visual en `/admin/dashboard` diferido** — la API HTTP y el CLI ya
  permiten operar manualmente; el toggle visual queda pendiente, igual que
  otros seguimientos de UI de BL-43.
- **Sin broadcast multi-instancia** — si la app corre con más de una réplica,
  cada proceso tiene su propio estado en memoria; activar en una instancia no
  detiene las demás. No es un escenario actual conocido del despliegue, pero
  queda anotado para cuando se revise.

## 9. Criterios de cierre

1. `EmergencyStopManager`: estado inicial inactivo, activar/desactivar con
   actor/reason obligatorios, auditoría (quién/cuándo/por qué).
2. `GovernedModelMixin.ainvoke` falla cerrado sin reservar budget ni llamar
   al proveedor cuando el reader reporta activo; no falla cuando el reader es
   `None` o está inactivo.
3. `GovernedInteractionRunner.prepare_execution_context` falla cerrado antes
   de construir el `ExecutionContext`.
4. `InteractionProcessor` trata `EmergencyStopActiveError` como
   `FAILED_CONTROLLED`, igual que `CostGovernanceError`.
5. API admin: 401 sin token válido, 422 con actor/reason en blanco, 200 en
   el camino feliz de activar/desactivar/status; nunca expone el token en la
   respuesta.
6. Test de privacidad: `reason` nunca llega a un atributo de telemetría.
7. `pytest tests/unit/`, `ruff check` y `mypy src/` en verde. Sin necesidad
   de PostgreSQL/Docker.
