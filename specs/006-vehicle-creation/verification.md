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

### Botones Sí/No (pregunta del E2E)

La interfaz Telegram de AgentOS **ignora los `callback_query`** de Telegram:
no soporta inline keyboards de forma nativa (verificado en el código de Agno;
Discord sí tiene botones HITL nativos, Telegram no). Alternativas: extender
el webhook para procesar callback_query (toca internals de Agno — proceso
ADR-001) o mantener confirmación textual. → Anotado como **BL-15** en el
backlog; para el MVP se mantiene texto.

### Estado

- Resultado: iteración 1 FAIL → fixes aplicados → **pendiente re-test**
- Resultado: pendiente

