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

- Fecha: —
- Resultado: pendiente
