# Spec: 006 — Vehicle Creation Tool

> **Backlog:** BL-4
> **Status:** implemented
> **Target:** El usuario registra vehículos desde Telegram sin SQL manual

---

## Requirement

Los vehículos se insertan hoy por SQL manual en los E2E. El usuario no puede
registrar un vehículo desde Telegram. Este spec añade el par
`propose_vehicle` / `execute_vehicle` (WRITE → ActionProposal + confirmación),
siguiendo el patrón de `src/agent/tools/maintenance.py`.

### Must Have

- `VehicleService.register_vehicle()` — método WRITE en el service (dominio puro)
- Detección de duplicados por matrícula normalizada (uppercase, solo
  caracteres alfanuméricos: sin espacios ni símbolos)
- Par `propose_vehicle` / `execute_vehicle` en `src/agent/tools/vehicles.py`
  - `propose_vehicle` NO escribe: valida input, crea propuesta `pending_confirmation`
  - `execute_vehicle` valida confirmación, ejecuta y audita
- Registro en `_init_domain_tools()` (`src/main.py`) → 13 tools
- Prompt skill actualizado (`prompts/skills/vehicle_maintenance.md`)
- Unit tests del service (mocks) + tests de seguridad de UserContext

### Should Have

- Duplicado por nickname idéntico → advertencia en la propuesta (no bloqueo)
- Provenance: `source_document_id` opcional (p.ej. del permiso de circulación)
- Formato de respuesta español consistente con el resto de tools de vehículos

### Won't Have

- Edición/borrado de vehículos (DESTRUCTIVE — otro spec si surge)
- Deduplicación difusa más allá de la normalización definida (uppercase y
  eliminación de todo carácter no alfanumérico)
- Validación de formato de matrícula por país (España vs genérica)

---

## Design

### Contexto existente (no hay que crear)

- `VehicleCreate` model — ya existe con validaciones (`year` 1900–2100)
- `VehiclesRepository.create()` — INSERT parametrizado ya existe
- `ActionProposalsRepository` — create / confirm / mark_executed ya existen
- Patrones de referencia: `maintenance.py` (propose/execute),
  `vehicles.py` (formateo de respuestas)

### Piezas nuevas

1. **Service** — `VehicleService.register_vehicle(user_context, data: VehicleCreate) -> Vehicle`
   - Normaliza `registration` (uppercase + `re.sub(r"[^A-Z0-9]", "", ...)` —
     solo letras y números; si queda vacío → None) y `nickname` (strip)
   - Comprueba duplicado de matrícula: `find_by_reference` con matrícula
     normalizada → si algún candidato coincide tras normalizar ambos lados,
     lanza `ValueError` (el tool lo captura y devuelve mensaje de error)
   - Delega en `VehiclesRepository.create()`
2. **Tools** — en `vehicles.py` (junto al resto de tools de vehículos):
   - `propose_vehicle(run_context, make, model, year?, registration?, nickname?, vin?, source_document_id?)`
     - `tool_name="register_vehicle"` en la propuesta (mismo convenio que
       `register_vehicle_maintenance`)
     - Devuelve resumen legible + pregunta de confirmación (patrón maintenance)
   - `execute_vehicle(run_context, proposal_id)` — patrón idéntico a
     `execute_vehicle_maintenance`: confirm → service → mark_executed
3. **Wiring** — 2 líneas en el bloque de vehículos de `_init_domain_tools()`
4. **Prompts** — añadir las 2 tools a `prompts/skills/vehicle_maintenance.md`
   (sección "Available Tools" + sección "Vehicle Registration" con el flujo
   de confirmación). ⚠️ Cambio evaluable — anotar en el commit.
5. **Tests** — `tests/unit/test_vehicle_service.py` (ampliar):
   - `register_vehicle` happy path (verifica normalización)
   - duplicado de matrícula → `ValueError`
   - `user_id` del contexto, no del input

### Decisión de gobernanza

`register_vehicle` es clasificación **WRITE** (crea dato canónico en
`ancora.vehicles`). No toca sistemas externos → no EXTERNAL_ACTION.
Por tanto: par propose/execute, sin permisos adicionales.

---

## Success Criteria

1. "Registra mi Ford Mondeo del 2019, matrícula 1234ABC" → `propose_vehicle`
   crea propuesta y muestra resumen con confirmación solicitada
2. Usuario responde "Sí" → `execute_vehicle` inserta en `ancora.vehicles`
   con `user_id` del canal
3. Matrícula duplicada (misma, con espacios o minúsculas) → error claro,
   sin escribir
4. `find_vehicle` con la matrícula nueva encuentra el vehículo creado
5. Sin `ANCORA_DATABASE_URL` → app arranca sin las tools (degradación graceful)
6. `pytest tests/unit/` verde (82 tests)
7. E2E Telegram probado y documentado en `verification.md` (o anotado en
   BACKLOG como pendiente — alimenta BL-1)
