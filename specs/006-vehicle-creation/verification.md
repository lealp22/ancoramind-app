# Verification: 006 — Vehicle Creation Tool

## Revalidación con consentimiento Core — 2026-10-17

**PASS del flujo manual autorizado** vía Playwright/Telegram: alta de un vehículo
ficticio sin matrícula/VIN → botón Sí → mantenimiento ficticio → botón Sí →
consulta de vehículo/historial. Cero filas antes de cada confirmación; al final
un vehículo, un mantenimiento y dos propuestas `executed`. Consulta final
`completed`, sin nuevas propuestas. Ambas confirmaciones con cero inferencia.

Baseline revisión 8/r4, sin retries/fallback ni cambios de producto/despliegue.
41 pruebas unitarias focales superadas. El vehículo ficticio queda identificado
y persistido; no se borró automáticamente ni se modificó un vehículo real.

Correlaciones, coste estimado y límites:
`specs/008-railway-deployment/mvp-release-campaign.md`, entrega 2.
No revalida factura/OCR, duplicados ni normalización de matrícula.
El historial siguiente describe la implementación legacy de septiembre;
`execute_vehicle` ya no se registra en el Agent: confirma/ejecuta el Core.

> Estado: **PASS** — completado 2026-09-06

## Escenario E2E (Telegram)

1. "Registra mi coche: Ford Mondeo 2019, matrícula 1234ABC"
   - [x] El agente llama `propose_vehicle` (no escribe)
   - [x] Muestra resumen con los datos y pide confirmación
   - [x] `action_proposals` tiene fila `pending_confirmation` (tool `register_vehicle`)

2. Usuario responde "Sí"
   - [x] `execute_vehicle` inserta en `ancora.vehicles` con `user_id` correcto
   - [x] Propuesta pasa a `executed`
   - [x] Respuesta confirma el alta

3. "¿Qué coches tengo?" / "busca 1234ABC"
   - [x] `find_vehicle` encuentra el vehículo recién creado

4. "Registra otro Ford Mondeo, matrícula 1234abc" (misma matrícula, minúsculas)
   - [x] Rechazo claro por duplicado, sin escribir

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

### Iteración 3 — 2026-09-06 (hallazgo: tool call malformado del proveedor)

`propose_vehicle` completó correctamente y creó la propuesta real
`ef768efc-3643-4546-b904-5c1dbacf0035`. Al responder "Sí", AgentOS devolvió
su error genérico antes de ejecutar `execute_vehicle`; la propuesta quedó
`pending_confirmation` y no se creó ningún vehículo.

El historial persistido por Agno muestra que el primer run contenía dos tool
calls en el mismo mensaje:

1. `{ "id": "<uuid generado por Agno>" }` — incompleto, sin `type` ni
   `function`; Agno añadió un resultado de error para una tool inexistente.
2. El `propose_vehicle` válido, que sí se ejecutó.

En el turno siguiente, OpenRouter rechazó el historial malformado antes de
que el modelo pudiera elegir `execute_vehicle` (`status=ERROR`,
`Provider returned error`). Entorno: Agno 2.9.0, modelo
`minimax/minimax-m3:free`, proveedor OpenRouter (backend GMICloud).

**Fix defensivo:** `SafeOpenRouter` filtra tool calls incompletos en
`_populate_assistant_message`, después de consolidar streaming y antes de que
Agno los ejecute/persista. Mantiene llamadas válidas y registra un warning.
Cubierto por tests con la forma exacta del fallo; 82 unit tests passing.

**Re-test:** reiniciar la app y enviar `/new`, porque la sesión de esta
iteración ya contiene el mensaje malformado. No se borra automáticamente la
propuesta real pendiente (dato de auditoría).

### Iteración 4 — 2026-09-06 (flujo principal PASS)

Tras reiniciar, el primer intento reutilizó la sesión contaminada de la
iteración anterior y falló. Después de enviar `/new`, el flujo completó:

1. `propose_vehicle` mostró la propuesta del Ford Mondeo 2019, matrícula
   `1234ABC`, y solicitó confirmación.
2. "Sí" → `execute_vehicle` respondió éxito.
3. `find_vehicle` encontró el Ford Mondeo por matrícula.

Verificación adicional en PostgreSQL:

- Propuesta `e3ca2015-a8ad-4993-94c4-f375191e5dfb`: `executed`, con
  `confirmed_at` y `executed_at`.
- Vehículo `8d7699a0-42e1-4dba-8cd0-475c0a64bf25`: Ford Mondeo 2019,
  matrícula canónica `1234ABC`, `user_id=452022640`.

**Observación UX:** `find_vehicle` tardó lo suficiente para que pareciera
bloqueado. Agno 2.9 envía `send_chat_action("typing")` una sola vez antes de
procesar; Telegram lo expira a los pocos segundos. La mejora recomendada es
refrescar periódicamente `typing` durante el run, no enviar un mensaje temporal
que ensucie el chat. Registrado como BL-17.

### Iteración 5 — 2026-09-06 (duplicado + corrección PASS)

1. Se propuso un Nissan Qashqai+2 2011 con matrícula `1234-abc`.
2. Tras confirmar, `execute_vehicle` rechazó el alta porque la matrícula
   normalizada `1234ABC` ya pertenecía al Ford Mondeo.
3. El usuario corrigió la matrícula a `1235-abc`; se creó una nueva propuesta.
4. Tras confirmar, el Nissan se registró correctamente.
5. `find_vehicle` encontró por separado `1235abc` (Nissan) y `1234abc` (Ford).

Verificación adicional en PostgreSQL:

- La propuesta duplicada `738c708f-0dd8-4121-937f-15eb019a9a80` quedó
  `confirmed` y sin `executed_at`: el usuario confirmó el intento, pero la
  operación canónica no se ejecutó.
- La propuesta corregida `78ce9421-defc-4beb-8f06-d11d141eb671` quedó
  `executed`.
- Solo existen los dos vehículos esperados para el usuario: Ford `1234ABC`
  y Nissan `1235ABC`; no hay fila duplicada.

### Botones Sí/No (pregunta del E2E)

La interfaz Telegram de AgentOS **ignora los `callback_query`** de Telegram:
no soporta inline keyboards de forma nativa (verificado en el código de Agno;
Discord sí tiene botones HITL nativos, Telegram no). Alternativas: extender
el webhook para procesar callback_query (toca internals de Agno — proceso
ADR-001) o mantener confirmación textual. → Anotado como **BL-15** en el
backlog; para el MVP se mantiene texto.

### Estado

- Resultado: iteración 1 FAIL (agente simulaba) → iteración 2 falla en SQL
  (fix aplicado) → iteración 3 falla por historial con tool call malformado
  (workaround aplicado) → iteración 4 flujo principal PASS.
- Resultado final: **PASS (4/4 escenarios + corrección de datos)**

