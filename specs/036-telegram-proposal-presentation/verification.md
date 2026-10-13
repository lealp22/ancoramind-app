# Verification: 036 — Evidencia previa y validación pendiente

> **Fecha de registro:** 2026-10-14.
> **Estado:** documentación únicamente. No hay implementación de BL-48.
> Las pruebas anteriores descritas aquí no validan la mejora de presentación.

## 1. Evidencia funcional aportada por el propietario

### Flujo trivial TODO — resultado esperado confirmado

1. Crear «Prueba Telegram 01» generó propuesta con botones Sí/No.
2. Pulsar Sí confirmó la ejecución.
3. Añadir «comprar café» sin campos opcionales inicialmente falló y no
   persistió. Tras actualizar el esquema, respondió que se había añadido
   sin pedir confirmación; la consulta mostró una sola tarea pendiente.
4. El propietario confirmó que completar, ejecutar `/new` y consultar
   completadas funcionaron como se esperaba.

Esto cubre un recorrido concreto de BL-46, no toda su matriz: no se probaron
en este intercambio notas ni reapertura ni todos los casos de revisión.

### Flujo revisable con descarte — correcto funcionalmente, redundante en UX

Petición: añadir «Renovar el seguro» con prioridad alta y vencimiento el
20 de octubre de 2026 a «Prueba Telegram 01».

- Agent: enumeró título, prioridad y vencimiento, y pidió confirmar.
- Core: añadió otro bloque con título, `high`, `2026-10-20T00:00:00`, TTL
  de 15 minutos y botones Sí/No.
- Pulsar No devolvió «Propuesta descartada».
- Consulta posterior: solo «Comprar café» completada; la rechazada ausente.
- La respuesta añadió que no había propuestas pendientes y ofreció
  reproponer la tarea descartada sin petición del usuario.

**Límite de evidencia:** no se recogió la traza de tools de ese último
turno. No se puede concluir que la afirmación de pendientes se hiciera sin
`list_pending_proposals`. Sí se observa contenido ajeno a la consulta y
una invitación innecesaria a rehacer lo rechazado.

## 2. Evidencia operativa anterior a esta documentación

Consultas y operación realizadas en esta conversación, antes de BL-48:

- Railway, `ancoramind-app` / `production`: deployment
  `8cdfccf0-17fd-4088-b88d-5a41346cea53`, estado SUCCESS, SHA
  `40159b7dc5960acb54ff6b824fcbc83eca874630`.
- Supabase canónico estaba en `0012_document_content_hash`, sin
  `action_proposals.consent_mode`. Alembic aplicó `0013_session_token_index`
  y `0014_write_trivial_consent_mode` al destino verificado.
- Consulta posterior confirmó revisión 0014, columna NOT NULL con default
  `explicit_confirmation`, CHECK de los dos modos y el índice de sesiones.
- `/health` y `/health/readiness` devolvieron HTTP 200 / `status=ok`.
- 44 unitarias específicas y 1332 unitarias globales pasaron. Hubo avisos
  de exportación de métricas al Collector local ausente, sin fallos de tests.
- Sin reinicio/redeploy ni fixtures productivos. No se ejecutaron fresh
  install, downgrade ni integración aislada en esa operación.

El contexto anterior sitúa la prueba, pero no es una validación futura de
BL-48 ni motivo para cerrar BL-47 o todos los pendientes de specs/035.

## 3. Verificación de este incremento documental

- Se crean `spec.md`, `tasks.md` y este registro; se enlazan desde BL-48.
- Toda tarea de implementación permanece sin marcar.
- Lectura final revisada; UTF-8, ausencia de espacios finales, referencias
  locales, unicidad de BL-48 y tareas de implementación pendientes verificadas.
- `git diff --check` limpio. No se ejecutan suites de código para este
  incremento exclusivamente documental.
- Código, prompts, migraciones y configuración quedan sin cambios.

## 4. Pendiente de implementar y verificar

- [ ] AC1–AC3: presentación única, respuesta mixta y varias propuestas.
- [ ] AC4–AC6: consulta tras descarte, pendientes explícitos y nueva petición.
- [ ] AC7: regresiones triviales (TODO/notas).
- [ ] AC8–AC9: horas/zonas, límites, escapado, payload/hash y consentimiento.
- [ ] Tests y gates tras la implementación.
- [ ] Evaluación de instrucciones y E2E real del SHA autorizado.

No se marca como superado un criterio de la mejora solo porque el circuito
de consentimiento anterior funcionó.