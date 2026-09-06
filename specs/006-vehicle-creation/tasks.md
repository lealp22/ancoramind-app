# Tasks: 006 — Vehicle Creation Tool

## Task Breakdown

### T1: Domain service
- [x] `VehicleService.register_vehicle(user_context, data: VehicleCreate) -> Vehicle`
- [x] Normalización: `registration` → uppercase, solo `[A-Z0-9]`
      (sin espacios ni símbolos); `nickname` → strip
- [x] Duplicado por matrícula normalizada (ambos lados normalizados) → `ValueError`
- [x] Delegación en `VehiclesRepository.create()` (ya existe — no tocar)
- [x] `normalize_registration()` como función de dominio (testable)

### T2: Tools (thin adapters en `src/agent/tools/vehicles.py`)
- [x] `propose_vehicle` — valida, crea ActionProposal (`tool_name="register_vehicle"`),
      devuelve resumen + confirmación (patrón `maintenance.py`)
- [x] `execute_vehicle` — confirm → service → mark_executed (patrón
      `execute_vehicle_maintenance`)
- [x] Docstrings con frases de ejemplo del usuario (español)
- [x] Captura de `ValueError` del service → mensaje de error al usuario
- [x] Añadido `_get_actions_repo()` en `vehicles.py` (solo existía en maintenance.py)

### T3: App wiring
- [x] Import + `tools.extend()` de las 2 tools en el bloque de vehículos de
      `_init_domain_tools()` (`src/main.py`) → **13 tools**
- [x] Log actualizado: "Vehicle tools registered: ..." incluir propose/execute_vehicle

### T4: Prompts (⚠️ cambio evaluable — anotar en commit)
- [x] `prompts/skills/vehicle_maintenance.md`: añadir `propose_vehicle` /
      `execute_vehicle` a "Available Tools" (renombrado a "Skill — Vehicles")
- [x] Nueva sección "Vehicle Registration" (flujo de confirmación,
      qué datos pedir: make/model obligatorios, resto opcionales)
- [x] **Skill activado** en `instructions.py` (estaba comentado — nunca se
      cargaba); test_instructions actualizado (4→5 bloques)

### T5: Tests
- [x] `test_register_vehicle` happy path — verifica normalización de matrícula
- [x] `test_register_vehicle_duplicate_registration` — `ValueError`, repo no llamado
- [x] `test_duplicate_comparison_is_normalized` — "AB-123CD" vs "ab 123 cd"
- [x] `test_no_registration_skips_duplicate_check`
- [x] `TestNormalizeRegistration` — parametrizado (7 casos)
- [x] Verificación de que `user_id` viene del `UserContext` (no del LLM)
- [x] `pytest tests/unit/` verde → **82 tests** (80 al cerrar T5 + 2 del
      workaround OpenRouter descubierto en E2E)

### T6: Verificación E2E
- [x] Telegram: crear vehículo con propose → "Sí" → execute
- [x] Telegram: `find_vehicle` con la matrícula nueva lo encuentra
- [ ] Telegram: intentar matrícula duplicada normalizada → rechazo sin escritura
- [ ] Documentar en `verification.md` (o anotar pendiente en BACKLOG — BL-1)
