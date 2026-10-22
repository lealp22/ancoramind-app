# Resultado del spike BL-56 — 2026-10-22

**Conclusión: viable con restricciones, no listo para activar en producción.**
ADR-007 sigue **Proposed**. No hay imports del prototipo en la aplicación, flags,
exporter productivo, conexión a Railway, cambio de Grafana ni inferencia real.
El exporter implementado es experimental: `scripts/phoenix_spike/exporter.py`.

## Reproducción y versiones

Desde un entorno del proyecto con sus dependencias y las opcionales de
`scripts/phoenix_spike/requirements.txt`:

```powershell
python -m scripts.phoenix_spike.run
python -m scripts.phoenix_spike.local_backend
python -m pytest tests/unit/test_phoenix_spike_exporter.py -q
```

Agno 2.9.0; instrumentor Agno 1.0.3; OpenInference instrumentation 0.1.57;
semantic-conventions 0.1.32; OTel SDK/exporter gRPC 1.44.0. `pip check` limpio.
Se reutilizó el venv existente (no se instaló ni cambió dependencias), ejecutando
procesos dedicados; no se probó instalación limpia en un venv nuevo.

Phoenix Docker `arizephoenix/phoenix:version-15.1.0`, digest observado
`sha256:cac4b2fbdb98320a23ca3aa7e31e23ad25fdde44a2f1892ce0a01fcc31898628`.
Backend aislado con SQLite desechable, **no** prueba de PostgreSQL/retención de
producción. Sólo puertos loopback, sin mounts, secretos locales efímeros, auth
ON y telemetría/recursos externos OFF. El lanzador elimina su contenedor en
`finally`; el contenedor de exploración manual también se eliminó.

## Q1–Q9: evidencia y límites

| # | Resultado |
|---|---|
| Q1 | **Sí, acotado.** Dependencias instaladas compatibles (`pip check`) y Agent real sobre HTTP `MockTransport`; no provider externo ni inferencia. No se demuestra instalación fresh. |
| Q2 | **Sí.** Factory/model wrapper gobernados existentes, snapshot/budget, `tool_choice=required`, sin `output_schema`/JSON mode; dos respuestas HTTP guionizadas ejecutan `lookup_synthetic` y `present_reply`. Resultado terminal validado; nada de esto evalúa semántica del LLM. |
| Q3 | **Sí.** `instrument(tracer_provider=...)`; provider global idéntico antes/después. Segundo provider metadata registra sólo su span y ningún atributo de contenido. Es prueba de aislamiento SDK, no tráfico live del Collector. |
| Q4 | **Sí para el run ensayado.** Inventario abajo; no se generaliza a todas las modalidades/tools/versiones. |
| Q5 | **Sí, prototipo.** Copia `ReadableSpan`, allowlist, máscara por esquema/patrón; errores descartan sólo ese span. Canarios y superficies laterales cubiertos; backend local ingiere 3 spans con `[DNI]`, sin DNI original. Fallo del sink en un run real guionizado deja la misma respuesta terminal; sin retry en el wrapper. |
| Q6 | **Parcial.** `llm.cost.total=0.001` se conserva en REST. Los otros spans con alias propio no aportan coste. No se demostró cálculo automático ni agregado/UI de coste: no confundir atributo recibido con facturación calculada. |
| Q7 | **Sí, local.** Sin auth REST devuelve 401; se crea system API key vía GraphQL local usando admin secret efímero. Exporter OTLP gRPC autentica con `authorization: Bearer <system-key>`; 3 spans visibles por REST. No se consultó clave productiva. |
| Q8 | **Medida, no SLO aprobado.** Última muestra: 50 runs por variante, baseline 56,230 ms/run y 1,694 MiB de pico Python; instrumentado 75,044 ms/run y 1,800 MiB. +18,814 ms (~33,5 %), +0,106 MiB. Otra muestra previa: 45,221→72,493 ms. Incluye construcción de Agent/esquemas/HTTP simulado/GC y avisos de historial sin DB; no red/backend export ni RSS del proceso. No se define aceptabilidad productiva. |
| Q9 | **Sí, procedimiento local.** `GET /v1/projects/spike/spans?attribute=user.id:<seudónimo>`, recoger `context.trace_id`, `DELETE /v1/traces/{trace_id}` → 204. Dos trazas objetivo borradas, cero spans de ese usuario y uno del otro conservado. En producción debe paginarse y coordinar pausa de captura; todas las spans de una traza deben pertenecer al mismo usuario. No borrar por nombres ni recorrer datos de usuarios ajenos. |

## Inventario observado (sólo nombres, sin contenido)

- `agent.name`, `agno.agent`, `agno.agent.id`, `agno.run.id`, `agno.tools`.
- `graph.node.id`, `graph.node.name`, `session.id`, `user.id`.
- `input.mime_type`, `input.value`, `output.mime_type`, `output.value`.
- `llm.model_name`, `llm.provider`, `llm.token_count.{prompt,completion,total}`.
- `llm.tools.{0,1}.tool.json_schema`.
- `llm.input_messages.{0,1}.message.{content,role}`;
  `llm.input_messages.2.message.role`,
  `llm.input_messages.2.message.tool_calls.0.tool_call.{id,function.name,function.arguments}`;
  `llm.input_messages.3.message.{content,role,tool_call_id}`.
- `llm.output_messages.0.message.role`,
  `llm.output_messages.0.message.tool_calls.0.tool_call.{id,function.name,function.arguments}`.
- `openinference.span.kind`, `tool.description`, `tool.name`, `tool.parameters`.
- El procesador sintético añade `ancora.capture.source`, `ancora.correlation_id`
  y `ancora.interaction_id`; ambos IDs del contexto real del run, iguales en sus
  spans; seudónimo HMAC separado generado localmente.

El exporter sólo conserva kind, IDs UUID de correlación, seudónimo, modelo,
contadores/costes finitos, mensajes textuales y parámetros JSON acotados de tools
sintéticas conocidas. Descarta blobs genéricos `input/output.value`, resources
originales, scope, eventos, links, tracestate del span/padre y descripciones de
error; nombre fijo por kind. 27 tests específicos del exporter superados.
Los objetos SDK originales permanecen intactos; el input HTTP conserva el canario
real y sólo la copia exportada lo enmascara. Corpus del detector sin modificar:
10 frases cotidianas, 0 positivos en esos controles; no estima FPR poblacional.

## Bloqueo arquitectónico y decisión propuesta

**NO integrar auto-instrumentación global tal cual.** Aunque el provider sea
independiente, el instrumentor parchea Agno a nivel de proceso. Campos admitidos
como `message.content`, mensajes tools o historial pueden contener documentos,
resultados de extracción o transcripciones. Una allowlist de nombres no determina
la procedencia del texto. El prototipo exige marcador `synthetic_text`; ese
marcador es una restricción experimental, no una autorización productiva.

Propuesta antes de implementar: seam manual de captura con procedencia confiable
en el adaptador gobernado de LLMAccess, excluyendo documentos/voz **antes** de
crear spans; historial mixto debe excluirse, no etiquetarse entero como seguro.
Si se conserva instrumentor, necesita demostrar esa exclusión igualmente y
versión fijada. No activar ambos caminos ni añadir bypass/retries.

Pendientes: aceptación explícita de ADR/enmiendas; resolver seam y coste/UI;
ensayar transporte/latencia con límites aceptados; inventario/DPIA/términos de
todos los autorizados; retención/borrado paginado; configuración privada y
fail-closed; integración productiva y sus pruebas; SHA/CI/despliegue/E2E propios.
Por esos límites T0 no se marca cerrado sin matices ni T4 productivo completado.

Gates finales compartidos con UX: 2211 unitarias/1 skip, 81,69 % cobertura;
218 integraciones locales/1 STT skip; Ruff/mypy186/catálogos45/diff limpios.
El backend local y el run gobernado sintético se repitieron con el exporter
final: ambos passed; sin contenedores de spike restantes. Sin commit/deploy por
este agente; revisar también el índice Git, que contiene cambios staged de
trabajo concurrente y puede no reflejar las últimas modificaciones del worktree.
