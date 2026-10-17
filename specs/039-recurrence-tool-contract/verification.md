# Verificación 039 — BL-54

2026-10-17. Diagnóstico y corrección locales, sin producción ni inferencia.

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

**Pendiente:** commit con indicación de cambio evaluable de prompts/descripciones,
CI del mismo SHA y autorización separada de rollout/E2E natural. Mantener BL-54
abierto para esa comprobación; tests deterministas no prueban obediencia del LLM
ni resuelven retrospectivamente el run histórico. Los cinco casos T7 de BL-48
no se amplían con calendario ni se ejecutan aquí: su aprobación deberá ligarse
al SHA/source fingerprint vigente después del commit, no al preflight anterior.