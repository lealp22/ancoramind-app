# Spec 039 — Contrato de recurrencia coherente (BL-54)

Estado: corrección desplegada y regresión natural E2E acotada superada el
2026-10-17 en SHA `778c5a3`. Causa histórica exacta no confirmada.
Alcance inicial: diagnóstico/corrección local. El propietario autorizó después
una petición natural Telegram y descarte, sin crear eventos ni avisos.

## Evidencia y límite causal

Antes de corregirlo, el schema real obtenido con `Function.from_callable`
describía `recurrence_until` como «ISO 8601 date» en calendario/recordatorios.
El prompt de calendario también recomendaba una fecha final, sin exigir hora
ni zona. Sin embargo `RecurrenceRule` rechaza cualquier `until` naive:
`2026-11-15` y `2026-11-15T10:00:00` no sirven. Ambas tools capturaban esos
errores y respondían con un mensaje orientado a frecuencia aunque `weekly`
sea válida; un intervalo inválido produce el mismo diagnóstico engañoso.

Reproducción sintética sin DB/proveedor: fecha-hora `+01:00` y UTC aceptadas;
fecha sola/naive, frecuencia desconocida e intervalo cero rechazados antes
de crear propuesta. Agno `FunctionCall.aexecute` con contexto inyectado y
offset válido también acepta, sin quitarlo en el adaptador. Esto demuestra
una contradicción del contrato, no los argumentos exactos del run histórico
`46021851-1eb1-49d3-bf61-d608a5086577`. No atribuir su causa al modelo o DST.

## Corrección acotada

- Alinear descripciones visibles de ambas tools con el Core: límite inclusivo
  fecha-hora ISO 8601 con zona explícita (offset o Z), nunca fecha sola/naive;
  intervalo entero 1–365, default 1. Preservar instantes/offsets explícitos.
- Prompt de calendario cargado: no recortar fecha-hora a fecha ni inventar
  hora/zona; pedir aclaración natural si falta información. Mantener la misma
  regla en el asset de recordatorios, sin cambiar qué prompts se cargan.
- Respuesta fija compartida para error de recurrencia: enum, rango y contrato
  de `until`, sin eco de entradas/excepciones ni acusar sólo a frecuencia.
  Indicar que no se creó propuesta; sin retry ni fallback nuevo.
- Regresiones de schema real Agno, parser y adapters directos/FunctionCall
  con mocks spec de repositorios: éxito con offset conservado; errores sin
  I/O; límites, ausencia de recurrencia y round-trip intactos.

## Invariantes y salida

No relajar validación ni convertir naive/date-only automáticamente. Sin
cambios en parser/expansión, payload/hash, permisos, consentimiento, ejecución,
zonas horarias, registro de tools, configuración ni observabilidad.
Cambio de descripciones/prompts evaluable: debe identificarse en el commit.
La fase local no autorizaba despliegues, inferencias ni lectura de runtime
personal. La validación posterior autorizada figura en `verification.md`.

Gates locales superados: unitarias/integración globales, Ruff, mypy y diff.
E2E natural autorizado superado para una petición con zona/límite explícitos
y descarte. Cierre acotado del defecto de contrato y su regresión, no causa
histórica confirmada ni garantía de toda recurrencia/obediencia semántica.
