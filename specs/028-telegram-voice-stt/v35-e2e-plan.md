# Plan E2E V35 — consentimiento por voz («Sí» / «No»)

> **Estado:** planificado el 2026-10-20, **no ejecutado**. Se hará en otra sesión.
> **Alcance:** sólo V35 de `acceptance.md`. V36 (benchmark) queda fuera.
> **Código:** no requiere cambios. Sólo envío de notas de voz por el propietario y
> verificación de lectura en Supabase.

## 1. Punto de partida (verificado 2026-10-20)

- El ejecutor está conectado: `_handle_voice_consent` → `resolve_voice_consent` →
  `_execute_claimed` → `ProposalExecutor.execute`. La nota de `spec.md` (~l.126-128)
  que dice que `_execute_claimed()` sólo informa está **obsoleta**.
- Producción tiene el consentimiento gobernado y la voz activos: hay propuestas
  `explicit_confirmation` ejecutadas por botón (última 2026-10-19 23:35 UTC). Se
  dedujo de los datos; no se leyeron variables de Railway (devuelven secretos).
- Había 0 propuestas `pending_confirmation` vigentes: una nota «Sí» no puede tomar una
  propuesta ajena. **Reconfirmar este punto antes de empezar.**

## 2. Reglas a respetar

- La propuesta debe estar **ya presentada** antes de enviar la nota (V25).
- Caduca 15 min tras la entrega (`CONSENT_TTL`); dejar margen.
- El parser sólo acepta un «Sí»/«No» aislado (punto o `!` final opcional). Un
  «Sí, por favor» no es consentimiento: cae al Agent como petición normal, que no
  tiene `execute_*`. Es seguro, pero hay que documentarlo si ocurre.
- Hablar claro, 1-2 s de audio. Coste ≈ 0,00003 USD de STT por nota.

## 3. Casos

| # | Acción en Telegram | Resultado esperado |
|---|---|---|
| A | Texto: «Crea una lista de tareas llamada V35 prueba»; esperar bloque con botones; nota «Sí» | Lista creada una vez; propuesta `executed`, `confirming_interaction_id` = interacción de voz; esa interacción con 0 llamadas de modelo y `agent_started_at` nulo |
| B | Texto: «Crea una lista llamada V35 descartar»; nota «No» | Propuesta `discarded`; lista no creada; 0 Agent |
| C | Sin propuesta pendiente; nota «Sí» | «No hay una única propuesta vigente…»; nada ejecutado |
| D (opcional) | Dos propuestas pendientes; nota «Sí» | Respuesta de aclaración; cero ejecuciones |

## 4. Verificación (sólo lectura, metadata-only)

1. `action_proposals` de la última hora: `status`, `consent_mode`, `presented_at`,
   `expires_at`, `confirming_interaction_id`.
2. Interacciones de voz + `voice_preparations`: `model_call_count`,
   `agent_started_at`, `estimated_cost` y latencia (`completed_at - received_at`; en
   V34 no se midió).
3. Efecto real: conteo en `todo_lists` (sin leer contenido personal).
4. Transcript purgado: `transcript_ciphertext` nulo tras `completed`.

## 5. Después de ejecutarlo

- Añadir la evidencia (y la latencia) a `verification.md`.
- Marcar en `tasks.md` el avance de «E2E V34–V36» (V36 sigue abierto).
- Corregir la nota obsoleta de `spec.md` (§1, `_execute_claimed()`).
- Borrar desde el bot las listas «V35 prueba» creadas.

## 6. Reversibilidad y límites

- Sin cambios de código ni de datos que revertir. Si algo sale mal, apagar
  `TELEGRAM_VOICE_ENABLED`.
- Una prueba E2E aislada no cierra BL-26: el gate de `acceptance.md` sigue exigiendo
  benchmark con umbrales previos, runbook/rollback y activación gradual.
