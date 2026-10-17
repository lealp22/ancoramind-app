# Verificación 038 — BL-49

2026-10-17. Implementación y validación locales seguidas de E2E autorizado.
El apartado local conserva el alcance y los gates de esa fase.

## Evidencia

- Regresiones del renderer reproducen la omisión antes del parche: frecuencia,
  intervalo, límite y aviso no aparecían; snooze no tenía nombre legible,
  duración ni contexto canónico. Tras el parche, 29 casos unitarios nuevos
  cubren renderer y composición Core en los dos módulos afectados.
- Recurrencias diaria/semanal/mensual/anual, intervalos unitarios/múltiples,
  límite inclusivo con offset intacto/sin límite, evento único, aviso OFF y
  antelación cero/positiva. Los defaults son los de ejecución, no del LLM.
- Snooze en minutos/horas/combinaciones; título canónico, target ausente o
  ID inválido; título de payload ignorado; límites por campo, una sola línea
  y escape HTML. Una lectura SQL fallida se propaga y cierra la sesión: no
  inventa target ni usa una inferencia/retry de reemplazo.
- Cuatro integraciones nuevas en `test_calendar_snooze_presentation.py`:
  objetivo propio/ajeno/inexistente y evento recurrente con aviso al inicio.
  Repositorios y PostgreSQL reales, sin Agno/Telegram/proveedores reales.
  La composición usa la identidad de la interacción y no filtra título ajeno;
  mantiene payload/hash y estado `pending_confirmation`, IDs de botones y
  respuesta independiente. No crea eventos ni recordatorios al presentar.

## Gates ejecutados

- `pytest tests/unit/ -q --tb=short`: **1582 passed**.
- `pytest tests/integration/ -q --tb=short`: **207 passed, 1 skipped**.
  Destino forzado: Docker PostgreSQL `127.0.0.1:5432`, base dedicada
  `ancoramind_test`; URL custom ignorada y `ANCORA_TEST_REQUIRE_DB=1`.
  `ANCORA_STT_SMOKE_APPROVED=0` fuerza exclusión de la inferencia live.
- Ruff global (`src/ tests/ scripts/ migrations/`): limpio.
- `mypy src/`: limpio, 175 módulos. `git diff --check`: limpio.
- Aviso de exportación OTLP a localhost:4318 sin Collector local en la suite
  unitaria; no es fallo funcional ni evidencia del Collector remoto.

## Límites y siguiente validación

Sin cambios de payload/hash, permisos, consentimiento, ejecutor, tools/prompts,
recurrencia, zonas horarias, notificaciones, migraciones ni configuración.
El título es contexto de lectura al presentar, no un nuevo campo del payload
ni una promesa de disponibilidad futura. Los textos largos conservan el
truncado existente de 120 caracteres por campo. «No disponible» no concede
acceso: la validación de propiedad en ejecución permanece intacta.

En la fase local: no despliegue ni SQL remoto, inferencia real, flags o E2E Telegram.
Para cierre operativo: autorizar SHA y ventana, comprobar CI del mismo SHA,
validar visualmente evento recurrente con límite/aviso y snooze con objetivo
y duración; registrar entrega/botones y resultado. No usar SQL como sustituto
de la revisión humana del bloque. BL-48 mantiene su alcance independiente.

## E2E Telegram autorizado — 2026-10-17

Código servido `65295ac02b32728d9c4207ecee64e980d6fb3c06`, ya desplegado por
el propietario en `2ced2ad2-f912-4846-81d8-19d096198cd8`. Durante la ventana
BL-52, nueva configuración de aviso produjo deployment
`a20e86e1-93b1-4949-82e1-663ae290e162` SUCCESS del mismo SHA. Checks CI del
mismo SHA verdes; runtime 8/r4, una réplica, sin tocar modelo ni prompts.

Alcance anunciado: presentar y **descartar** dos propuestas, sin confirmar
escrituras canónicas ni programar avisos. Playwright observó el bloque recibido
en Telegram, no sólo el payload SQL; el propietario puede revisarlo en el chat.
No se atribuye a esa automatización una aprobación humana formal de toda la UX.

| Paso | Origen / propuesta / salida | Resultado |
|---|---|---|
| Petición natural inicial | `46021851-1eb1-49d3-bf61-d608a5086577`; entrada `496`, salida `497` | completed con rechazo de recurrencia comunicado por tool; cero propuestas y cero eventos |
| Nueva petición explícita con parámetros UTC | `4dfbebb5-fda9-418b-a98c-5be23b5680d7`; propuesta `35e8adac-2491-45e8-a1fb-d82a01acca52`; entrada `499`, salida `500` | bloque Core único con frecuencia/intervalo, límite inclusivo, aviso y antelación |
| Descarte calendario por No | `9cab05c4-4347-49e8-a42b-76a21e4a6b11`; salida `501` | propuesta discarded, executed_at NULL, cero IA |
| Snooze de fixture existente propio | `792e94cb-88d5-451f-86ee-43032a8d88e5`; propuesta `d887083a-f278-4de1-9182-03b7b0f78539`; entrada `502`, salida `503` | título canónico y duración presentes, sin UUID en el bloque del bot |
| Descarte snooze por No | `b3387df8-d61e-415b-9eac-3f8d7b9c8d7d`; salida `504` | propuesta discarded, executed_at NULL, cero IA |

Calendario observado: título sintético BL49, inicio `2026-11-01T09:00:00+00:00`,
fin `09:01`, cada 2 semanas, hasta `2026-11-15T09:00:00+00:00` inclusive,
aviso sí y «1 h 30 min antes del inicio». Snooze observado: «Posponer
recordatorio», objetivo `Recordatorio: Prueba calendario E2E 20261017` y
«1 h 30 min desde la confirmación». El prefijo del campo más el título
produce el doble «Recordatorio:» ya conocido; no se corrigió en esta ventana.

IDs visuales Telegram: calendario `14439–14441`, snooze `14442–14444`;
no son los message_id Bot API de la tabla. Capturas locales acotadas de los
dos bloques en la salida Playwright, sin capturar el historial completo.
Sin migración BL-49 ni mutaciones SQL; SELECT scoped de auditoría verificó
payloads y hashes originales, ambos discarded, cero evento con el título nuevo
y cero recordatorios con source_action_id de las dos propuestas.

Uso: cada una de las tres peticiones al Agent consumió 2 model calls /
2 Gateway requests / 2 tool calls, incluida la terminal. Total 6/6/6,
**0,00805790 USD estimados**, coste real NULL, rev.8/r4, retry_count=0 y sin
fallback. Descartes 0/0/0. La segunda petición de calendario fue un mensaje
nuevo anunciado tras comprobar que no existía propuesta: no replay/retry
automático de un run incierto ni ocultación del primer fallo.

Límites: PASS de presentación/descarte de esos dos bloques, no de ejecución
nueva, entrega de recordatorios, todas las frecuencias ni del caso natural
inicial. Este último se registra BL-54: entradas proporcionadas con offset
válidas en el helper local; no se inspeccionaron argumentos privados reales
de la tool ni se determinó aún dónde se perdió/cambió la recurrencia. No
atribuir causa al timezone/modelo sin evidencia. No ampliar BL-48 ni lanzar
evals T7. Navegador queda abierto; ninguna propuesta de esta ventana pendiente.
