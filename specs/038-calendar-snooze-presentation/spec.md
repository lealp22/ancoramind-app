# Spec 038 — Presentación revisable de calendario y snooze (BL-49)

Estado: desplegado; E2E Telegram de presentación y descarte superado el
2026-10-17. Primera petición natural de recurrencia rechazada: hallazgo BL-54.
Alcance local autorizado por el propietario. Evidencia en `verification.md`.

## Requisito y diseño

El bloque Core debe permitir revisar la acción sin consultar SQL ni confiar
en la narración del modelo. Calendario mostrará frecuencia/intervalo, límite
inclusivo de recurrencia (o sin límite), creación o ausencia de aviso y su
antelación (incluido cero: al inicio). Se mantienen inicio/fin y sus offsets
almacenados, sin reinterpretar zonas horarias ni cambiar recurrencias.

Snooze mostrará «Posponer recordatorio», objetivo legible y duración desde
la confirmación, sin prometer un instante calculado antes de ejecutar. El
Core resolverá el título con `RemindersRepository.get_by_id(user_id, id)`
al componer la respuesta. Esa lectura es sólo contexto de presentación:
no modifica el payload `{reminder_id, minutes}`, su hash, los permisos, los
botones ni las validaciones del ejecutor. No se acepta un título del LLM
como sustituto. Si no existe/no pertenece al usuario o falta un ID válido,
se muestra «No disponible» sin consultar datos de otro usuario ni inventar
el target. Un error de lectura no se oculta mediante fallback inferencial.

El renderer sigue siendo puro. Los valores nuevos siguen los límites de
longitud/línea existentes y pasan por el renderer HTML de Telegram vigente.
Las propuestas antiguas usan los defaults de ejecución existentes (intervalo
1, sin aviso, antelación 0); un snooze sin contexto muestra el fallback.

## Criterios de aceptación

- Recurrencias diaria/semanal/mensual/anual con intervalos 1 y mayores,
  límite explícito con hora/offset intactos y sin límite.
- Evento único, aviso desactivado y aviso con antelación cero/positiva.
- Snooze: minutos, horas y combinaciones; objetivo canónico acotado,
  ausente/no propio e ID inválido, sin usar título aportado en payload.
- Payload/hash, botones y partición answer/proposal_text sin cambios.
- Regresión de composición Core y aislamiento con PostgreSQL local dedicado.
- Gates locales: unitarias globales, integración local, Ruff, mypy y diff.

## Fuera de alcance

No cambios de permisos, consentimiento, tools/prompts, cálculo de fechas,
ejecución, recurrencia, notificaciones outbound, contabilidad ni migraciones.
No despliegue, inferencia real, activación de flags ni E2E Telegram implícitos.
Revalidación Telegram autorizada ejecutada para presentación/descarte; no
certifica ejecución nueva ni toda la UX natural (BL-54). Ver `verification.md`.
