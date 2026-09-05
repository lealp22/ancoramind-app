# Tasks: 006 — Vehicle Creation Tool

## Task Breakdown

### T1: Domain service
- [ ] `VehicleService.register_vehicle(user_context, data: VehicleCreate) -> Vehicle`
- [ ] Normalización: `registration` → uppercase sin espacios; `nickname` → strip
- [ ] Duplicado por matrícula normalizada → `ValueError` con mensaje claro
- [ ] Delegación en `VehiclesRepository.create()` (ya existe — no tocar)

### T2: Tools (thin adapters en `src/agent/tools/vehicles.py`)
- [ ] `propose_vehicle` — valida, crea ActionProposal (`tool_name="register_vehicle"`),
      devuelve resumen + confirmación (patrón `maintenance.py`)
- [ ] `execute_vehicle` — confirm → service → mark_executed (patrón
      `execute_vehicle_maintenance`)
- [ ] Docstrings con frases de ejemplo del usuario (español)
- [ ] Captura de `ValueError` del service → mensaje de error al usuario

### T3: App wiring
- [ ] Import + `tools.extend()` de las 2 tools en el bloque de vehículos de
      `_init_domain_tools()` (`src/main.py`)
- [ ] Log actualizado: "Vehicle tools registered: ..." incluir propose/execute_vehicle

### T4: Prompts (⚠️ cambio evaluable — anotar en commit)
- [ ] `prompts/skills/vehicle_maintenance.md`: añadir `propose_vehicle` /
      `execute_vehicle` a "Available Tools"
- [ ] Nueva sección "Vehicle Registration" (flujo de confirmación,
      qué datos pedir: make/model obligatorios, resto opcionales)

### T5: Tests
- [ ] `test_register_vehicle` happy path — verifica normalización de matrícula
- [ ] `test_register_vehicle_duplicate_registration` — `ValueError`, repo no llamado
- [ ] Verificación de que `user_id` viene del `UserContext` (no del LLM)
- [ ] `pytest tests/unit/` verde

### T6: Verificación E2E
- [ ] Telegram: crear vehículo con propose → "Sí" → execute
- [ ] Telegram: `find_vehicle` con la matrícula nueva lo encuentra
- [ ] Documentar en `verification.md` (o anotar pendiente en BACKLOG — BL-1)
