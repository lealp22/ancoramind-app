# Verificación 039 — BL-54

2026-10-17. Diagnóstico/corrección locales y posterior E2E natural autorizado.
Los apartados iniciales conservan evidencia y límites de la fase local.

## Qué se demostró

1. Antes del cambio, `Function.from_callable(propose_calendar_event)` y la
   tool de recordatorios publicaban `recurrence_until` como «Optional ISO 8601
   date». No era sólo una lectura del docstring: se inspeccionó el schema
   generado por el Agno instalado. El prompt de calendario cargado también
   recomendaba una fecha final sin requisitos de hora/zona.
2. `recurrence_rule_from_flat` convierte fecha sola en datetime naive, y el
   validador `RecurrenceRule._until_must_be_aware` la rechaza. Con frecuencia
   válida weekly, fecha sola/naive o intervalo cero disparaban el mismo mensaje
   orientado a frecuencia. `+01:00` y UTC completos se aceptan.
3. El adapter directo y `FunctionCall.aexecute` con contexto inyectado y sin
   modelo conservan el offset válido y generan únicamente una propuesta mock.
   No hay una pérdida de offset determinista en ese camino reproducido.

Esto demuestra un contrato incoherente y un error poco útil, no la causa exacta
del run histórico `46021851-1eb1-49d3-bf61-d608a5086577`. No se consultaron
argumentos/runtime privados del run ni se repitió inferencia para adivinarlos.
Frecuencia desconocida, intervalo y límite inválidos son hipótesis compatibles;
no afirmar que el LLM recortó la fecha o que el Core falla con `+01:00` válido.

## Cambio y prueba de regresión

- Dos docstrings de tools: límite inclusivo, datetime con offset/Z, ejemplo,
  sin fecha sola/naive e intervalo 1–365. Tipos y campos required sin cambios.
- Prompt de calendario: preservar hora/zona explícitas y pedir aclaración
  natural si faltan; no inventar medianoche/UTC ni omitir el límite. Mismo
  contrato en el asset de recordatorios, sin cargar nuevos bloques de prompt.
- Error `INVALID_RECURRENCE` compartido, fijo y sin eco de entradas/excepciones:
  explica todas las restricciones y ausencia de propuesta. No incorpora retry.
- 44 casos nuevos en `tests/unit/test_recurrence_tool_contract.py`: schema real,
  contrato cargado, fecha sola/naive/malformada, rango de intervalo y frecuencia,
  no DB al rechazar, offset y UTC a través de ambos adapters, round-trip,
  límites 1/365 y ausencia de frecuencia sin cambios. Agno success significa
  que la función devolvió texto, no que haya creado una propuesta.
- Antes del parche: **16 failed, 18 passed** en las 34 regresiones iniciales.
  Fallos exclusivamente en schema/prompts/error esperados, mientras la matriz
  de offsets válidos ya pasaba. Luego se añadieron 10 controles adicionales.
- Selección inicial de cinco módulos: 114 passed antes de añadir los últimos
  dos controles de FunctionCall; la suite global posterior incluye los 44.

## Gates y límites

- Unitarias globales: **1626 passed**.
- Integración global: **207 passed, 1 skipped** en PostgreSQL Docker loopback,
  base dedicada `ancoramind_test`, URL custom ignorada, REQUIRE_DB=1 y
  `ANCORA_STT_SMOKE_APPROVED=0`; sin destino ni fixtures productivos.
- Ruff global `src/ tests/ scripts/ migrations/`: limpio.
- `mypy src/`: limpio, 175 módulos. Diff check limpio.
- Avisos OTLP a localhost:4318 sin Collector local; no afectan aserciones ni
  evidencian el estado del Collector remoto.

Sin cambio de parser, payload/hash, expansión, timezone, permisos, consentimiento,
ejecutor, registro de capabilities, telemetría o migraciones. No red a Telegram,
Gateway o producción; no replay de updates. Ninguna nueva inferencia real ni
provider físico. Navegador y flags no se tocaron.

**Pendiente al cerrar la fase local:** commit de cambio evaluable de prompts/descripciones,
CI del mismo SHA y autorización separada de rollout/E2E natural. Mantener BL-54
abierto para esa comprobación; tests deterministas no prueban obediencia del LLM
ni resuelven retrospectivamente el run histórico. Los cinco casos T7 de BL-48
no se amplían con calendario ni se ejecutan aquí: su aprobación deberá ligarse
al SHA/source fingerprint vigente después del commit, no al preflight anterior.

## Validación natural Telegram autorizada — 2026-10-17, 12:24–12:26Z

- El propietario confirmó que los cambios estaban desplegados y autorizó
  continuar las pruebas. Árbol limpio al comenzar; HEAD y código servido
  `778c5a3ec0d7dd929585b2a45151357dbb1cba13`, deployment
  `1193d431-a2f8-4536-ba73-0c1c7895e865` SUCCESS, una réplica.
- Checks `quality`, `integration`, `collector-config` success para ese SHA,
  revalidados. Sin staged changes. Readiness inicial 200, runtime rev.8,
  head Alembic 0017. Cero eventos/propuestas con el título sintético antes.
- Una única petición en lenguaje natural: evento «Prueba natural BL54
  20261017», 1/11/2026 a las 10:00–10:01, cada dos semanas hasta el
  15/11/2026 a las 10:00 inclusive; todas las horas UTC+01:00; aviso 90 min
  antes. Sin nombres de parámetros técnicos ni fecha-hora ISO escrita por
  el operador; zona y límite explícitos para no introducir ambigüedad nueva.
- Playwright envió el mensaje una vez y observó el bloque Core en Telegram:
  inicio/fin y límite con `+01:00`, cada 2 semanas, aviso sí y «1 h 30 min
  antes del inicio». Sin rechazo de recurrencia ni aclaración adicional.

| Paso | Identidad y resultado |
|---|---|
| Origen | `c6e99224-8bdf-4a7d-994f-481958949610`, update `978199116`, entrada Bot API `509`, completed 12:24:52.404976Z |
| Propuesta | `07fb5ef6-ed21-4ef1-ad4e-4c5b321a670e`, create_calendar_event, presentada 12:24:52.166136Z, salida Bot API `510` |
| Descarte No | `100291fc-a0c1-43cf-a404-50fa3ba2f367`, callback update `978199117`, salida `511`, completed 12:25:12.256573Z; sin IA |

Payload scoped al usuario: start `2026-11-01T10:00:00+01:00`, end
`2026-11-01T10:01:00+01:00`, weekly/2/until
`2026-11-15T10:00:00+01:00`, with_reminder=true y lead=90. Hash recomputado
igual al persistido: `538f2773c45b4b9e37daf84682dff5117b900a82fdc35d46501481bba5fe6da3`.
Una propuesta, discarded tras pulsar No, executed_at NULL; cero eventos con
el título y cero recordatorios con su source_action_id, antes y después.
No se pulsó Sí, no hubo mutaciones SQL ni limpieza de registros de auditoría.

Navegador principal IDs visuales `14447–14449` (petición/propuesta/descarte),
no confundir con Bot API. Confirmación visible «Propuesta descartada» y
borrador vacío; ambas pestañas Telegram se conservan abiertas.

Uso de la única petición: 2 model calls / 2 Gateway requests / 2 tool calls,
incluida presentación terminal; runtime 8/r4, dos eventos de uso completed,
retry_count=0, fallback=false. **0,00249900 USD estimados**, real NULL.
Descarte: agent_started_at NULL, 0/0/0 y cero eventos de uso.

Cierre: readiness 200 a 12:25:56Z, componentes healthy salvo circuit unknown;
panel HTTP 200 y API pairing sin token 401. App online, una réplica y sin
trabajo staged/applying. Head 0017, cero propuestas pendientes de este origen
verificados a 12:26:03Z. Sin cambios de flags, secretos, allowlist, modelo,
webhook ni migraciones/despliegues efectuados por el agente en esta ventana.
Panel/pairing/aviso conservan configuración previa ON, sin rollback automático.

93 unitarias focales superadas después de la prueba (contrato, parser, tools
y prompts), Ruff global y mypy src (175 módulos) limpios; diff check limpio.
La suite completa 1626/207 + 1 skipped conserva su ejecución
local anterior; no se presenta como una nueva ejecución de integración aquí.

**PASS y cierre acotado de BL-54:** contrato coherente y una regresión natural
superada con zona/límite explícitos. No demuestra retrospectivamente los
argumentos del fallo original, ni corrección causal exclusiva del prompt;
no benchmark estadístico, ejecución/entrega nueva, prueba de todas las
frecuencias, recordatorios naturales o límites ambiguos. No se repitieron
mensajes ni se ejecutaron las cinco evals T7; su autorización sigue separada.
