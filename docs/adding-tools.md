# Guía: Añadir una Tool nueva a AncoraMind

> La definición del agente (`create_ancora_agent()` en `src/agent/ancora_agent.py`)
> **NUNCA se modifica** al añadir capabilities. Las tools se inyectan como lista
> en `src/main.py::_init_domain_tools()`. Esto es el principio §2.2 de AGENTS.md:
> *"añadir capability ≈ añadir Tool"*.

## Cómo descubre Agno las tools

- **Tool = función Python plana async.** Agno genera el schema que ve el LLM a
  partir del **docstring y los type hints** de la función. No hay registro manual.
- **`run_context: RunContext` como primer parámetro** → inyectado automáticamente
  por Agno, no aparece en el schema del LLM (no es "elegible" por el modelo).
- La identidad del usuario se resuelve con `UserContext.from_run_context(run_context)`
  — NUNCA del input del LLM (principio §2.3).

## Checklist paso a paso

### 1. Dominio (lógica de negocio — sin imports de Agno*)

- `src/domain/<dominio>/models.py` — modelos Pydantic de entrada/salida
- `src/domain/<dominio>/service.py` — servicio con repositorios inyectados por constructor
- Si el dominio ya existe, solo añadir el método al service

### 2. Repositorio (si hay persistencia nueva)

- `src/repositories/<dominio>.py` — SQLAlchemy async, solo `text()` con bind params
- Toda query scoped por `user_id`
- Tablas nuevas → añadir a `migrations/init.sql` (idempotente, `IF NOT EXISTS`)

### 3. Tools (thin adapters)

- `src/agent/tools/<dominio>.py` — funciones async planas que delegan en el service
- El **docstring es la descripción que ve el LLM**: incluir cuándo usar la tool
  y ejemplos de frases del usuario (en el idioma del usuario)
- Devolver strings formateados en español (título en negrita, emojis moderados)
- **Operación WRITE/EXTERNAL_ACTION → par `propose_*` / `execute_*`** con
  ActionProposal (patrón de `src/agent/tools/maintenance.py`). La tool
  `propose_*` NO escribe nada canónico; `execute_*` valida confirmación, ejecuta y audita

### 4. Registro en main.py

En `_init_domain_tools()` (dentro del bloque condicionado a
`ANCORA_DATABASE_URL` — degradación graceful gratis):

```python
from src.agent.tools.<dominio> import mi_tool

tools.extend([mi_tool])
logger.info("Domain tools registered: mi_tool")
```

No tocar nada más: `create_app()` ya extiende esa lista al agente.

### 5. Prompts (comportamiento del agente — el cambio real)

- `prompts/tool_contract.md` — describir la nueva tool y sus reglas de uso
- `prompts/skills/<dominio>.md` — si es capability nueva (patrón: `skills/vehicle_maintenance.md`)
- ⚠️ **Cambiar prompts = cambio evaluable** (gobernanza, §10.4). Anotarlo en el commit.
- Sin actualizar prompts la tool es *descubrible* (Agno la envía en la petición),
  pero el LLM no sabe cuándo usarla ni con qué criterios

### 6. Tests

- Unit tests mockeando repositorios (`AsyncMock(spec=Repo)`) — patrón: `test_notes_service.py`
- Seguridad: test de que el service usa `UserContext` del canal, no input del LLM
- Ejecutar `pytest tests/unit/` antes de dar nada por terminado

### 7. Verificación E2E (si aplica)

- Escenario manual documentado en el `verification.md` del spec correspondiente
- Anotar en `BACKLOG.md` si queda pendiente de validar

## Checklist rápido (TL;DR)

```
[ ] models.py + service.py (domain, sin Agno)        ← si dominio nuevo
[ ] repository (text() parametrizado, user-scoped)   ← si persistencia nueva
[ ] tablas en migrations/init.sql                    ← si tablas nuevas
[ ] tool(s) en src/agent/tools/ (docstring cuidadoso)
[ ] propose_*/execute_* si WRITE                     ← con ActionProposal
[ ] registro en _init_domain_tools() (main.py)
[ ] prompts/tool_contract.md (+ skill si aplica)
[ ] unit tests (mocks, UserContext enforcement)
[ ] pytest tests/unit/ verde
```

## Qué NO hay que tocar

- `src/agent/ancora_agent.py` (definición del agente)
- `create_app()` en `main.py` (solo `_init_domain_tools()`)
- `src/config.py` (salvo que la tool necesite env vars nuevas)
- La interfaz Telegram / AgentOS
