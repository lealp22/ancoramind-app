# Verification: 006 — Vehicle Creation Tool

> Estado: pendiente (se completa con el E2E de Telegram — ver T6 en tasks.md)

## Escenario E2E (Telegram)

1. "Registra mi coche: Ford Mondeo 2019, matrícula 1234ABC"
   - [ ] El agente llama `propose_vehicle` (no escribe)
   - [ ] Muestra resumen con los datos y pide confirmación
   - [ ] `action_proposals` tiene fila `pending_confirmation` (tool `register_vehicle`)

2. Usuario responde "Sí"
   - [ ] `execute_vehicle` inserta en `ancora.vehicles` con `user_id` correcto
   - [ ] Propuesta pasa a `executed`
   - [ ] Respuesta confirma el alta con el ID

3. "¿Qué coches tengo?" / "busca 1234ABC"
   - [ ] `find_vehicle` encuentra el vehículo recién creado

4. "Registra otro Ford Mondeo, matrícula 1234abc" (misma matrícula, minúsculas)
   - [ ] Rechazo claro por duplicado, sin escribir

## Resultado

### Iteración 1 — 2026-09-05 (FAIL — hallazgos valiosos)

| Escenario | Resultado |
|---|---|
| 1. "Registra mi coche: Ford Mondeo 2019, matrícula 1234ABC" | ❌ El agente **escenificó** la propuesta (escribió el resumen + confirmación) **sin llamar a `propose_vehicle`** — verificado: 0 filas en `action_proposals` |
| 2. "Sí" | ❌ `execute_vehicle failed` — no había propuesta que confirmar; el LLM alucinó el recovery ("intento con VIN...") sin llamar a ninguna tool |
| 3-4. | No alcanzados |

**Diagnóstico:** el LLM imitó el formato de la propuesta por el pattern del
skill pero no invocó la tool. La BD confirma que no se creó ninguna propuesta.

**Fixes aplicados (iteración 2):**
1. `propose_vehicle`: el output incluye instrucción explícita de encadenamiento
   ("cuando el usuario confirme, llama execute_vehicle con este ID exacto")
2. `execute_vehicle` (propuesta no encontrada): mensaje que prohíbe inventar
   IDs y ordena re-proponer primero
3. Skill: "You MUST call propose_vehicle — NEVER write a proposal summary
   yourself" (también para maintenance)
4. `tool_contract.md`: nueva regla 11 — "Never simulate tool calls or their
   results" (⚠️ cambio evaluable)

### Iteración 2 — 2026-09-06 (hallazgo: bug de sintaxis SQL)

La tool ahora **sí se invoca** (fix del skill funcionó) pero falla el INSERT:
`PostgresSyntaxError: syntax error at or near ":"` — SQLAlchemy + asyncpg no
traduce `:param::jsonb` (confunde el cast con el bind param). Afectaba a 3
repos: `actions.create`, `documents.create_extraction`,
`maintenance.create` — es decir, **todos los propose_* y la extracción IA
habrían fallado** (por eso M3–M5 no estaban validados en E2E).

**Fix:** `CAST(:param AS jsonb)` en los 3 puntos. Verificado con repro
contra la BD real: propuesta creada OK (`pending_confirmation`).
80 unit tests passing.

### Botones Sí/No (pregunta del E2E)

La interfaz Telegram de AgentOS **ignora los `callback_query`** de Telegram:
no soporta inline keyboards de forma nativa (verificado en el código de Agno;
Discord sí tiene botones HITL nativos, Telegram no). Alternativas: extender
el webhook para procesar callback_query (toca internals de Agno — proceso
ADR-001) o mantener confirmación textual. → Anotado como **BL-15** en el
backlog; para el MVP se mantiene texto.

### Estado

- Resultado: iteración 1 FAIL (agente simulaba) → iteración 2 falla en SQL
  (fix aplicado y verificado) → **pendiente re-test iteración 3**
- Resultado: pendiente

