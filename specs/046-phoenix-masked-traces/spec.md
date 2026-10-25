# Spec 046 — Trazas con contenido enmascarado en Phoenix

Estado: ADR-007 **Accepted** (2026-10-23) para implementar detrás de flag OFF.
La activación en producción sigue sujeta al gate de esta spec.

**Decisión 2026-10-23:** captura **manual** en el adaptador gobernado de
`LLMAccess` con procedencia de texto; la auto-instrumentación global de Agno
queda descartada para producción. T6 se reformula en consecuencia.

**2026-10-22:** trabajo experimental autorizado, no integración: masking puro ya
existente + `scripts/phoenix_spike/` sólo sintético y `spike-result.md`. ADR sigue
Proposed; nuevas restricciones de procedencia/coste/medición pendientes. No hay
conexión entre app y Phoenix ni nuevos settings productivos.

## Problema

Ante un fallo concreto (p. ej. `InvalidPresentationOutputError`) solo queda un
contador: ni PostgreSQL ni Grafana conservan qué vio el modelo. Hace falta poder
reconstruir una petición sin romper el principio 11 (observabilidad sin
contenido) fuera del pipeline de Phoenix.

## Estado de partida (2026-10-20)

- Phoenix 15.1.0 + Postgres propio desplegados en Railway (proyecto
  `ancoramind-app`), sin conexión con la app. Auth activa, retención 30 días,
  `PHOENIX_TELEMETRY_ENABLED=false`.
- `src/observability/telemetry.py` crea su `TracerProvider` sin registrarlo como
  global, así que un segundo provider independiente es viable.
- No existe código de Phoenix, enmascarado ni dependencias `openinference`.

## Alcance

Un pipeline de trazas separado: instrumentación → `TracerProvider` propio →
exporter envolvente (allowlist + enmascarado, fail-closed) → Phoenix.

Fuera de alcance: evals en Phoenix (specs/044), datasets, prompts gestionados,
NER (Presidio), captura de audio/adjuntos/documentos, cualquier cambio en el
pipeline de Grafana y cualquier uso de Phoenix como fuente de verdad.

## Decisiones

1. **Flag** `PHOENIX_TRACING_ENABLED`, default `false`, fail-open: un fallo de
   Phoenix, del enmascarador o de red nunca afecta a Telegram, Core ni inferencia.
2. **Pipeline aislado.** Provider y exporter propios; los spans de Phoenix no
   pasan por el Collector. Test que lo garantiza.
3. **Allowlist** de atributos OpenInference en el exporter: lo no listado se
   descarta. Audio, adjuntos, documentos, `ai_extractions` y secretos quedan
   excluidos por construcción.
4. **Enmascarado solo en telemetría**, en tres capas (esquema → patrón con
   validación → red de seguridad numérica), con marcadores tipados sin dígitos.
   Tabla de detectores en ADR-007.
5. **Fail-closed por span:** si el enmascarador falla, el span no se exporta.
6. **Correlación:** atributos `ancora.correlation_id` e `ancora.interaction_id`.
7. **Usuario:** HMAC-SHA256 truncado de `telegram_user_id` con prefijo de dominio
   propio (`phoenix-user-v1:`). Clave propia e independiente
   (`PHOENIX_USER_PSEUDONYM_KEY`, decisión del propietario 2026-10-20), no
   derivada de ningún otro secreto: rotar otras claves no altera los seudónimos
   de Phoenix. Rotarla rompe la agrupación histórica por usuario; documentarlo.
8. **Transporte:** red privada de Railway; la app nunca usa el dominio público.
9. **Usuarios cuyo texto entra:** todos los usuarios autorizados, sin lista
   adicional (decisión del propietario, 2026-10-20). Consecuencia: el texto de
   terceros del piloto también se guarda enmascarado, así que los términos del
   piloto y el inventario de privacidad deben decirlo antes de activar el flag
   (ver Gate de activación). Los rechazados (`rejected`/`ignored`) no ejecutan el
   Agent y por tanto no generan trazas.
10. **Retención:** 30 días (valor ya configurado en Phoenix). Borrado por usuario:
    procedimiento documentado, ejecutable desde la UI/API de Phoenix filtrando por
    el seudónimo.

## Configuración nueva

| Variable | Default | Notas |
| --- | --- | --- |
| `PHOENIX_TRACING_ENABLED` | `false` | Interruptor general |
| `PHOENIX_COLLECTOR_ENDPOINT` | vacío | URL privada de Phoenix |
| `PHOENIX_API_KEY` | vacío | Secreto; solo en Railway |
| `PHOENIX_USER_PSEUDONYM_KEY` | vacío | Secreto (≥32 bytes aleatorios) para el HMAC de usuario; solo en Railway |
| `PHOENIX_PROJECT_NAME` | `ancoramind` | Proyecto en la UI de Phoenix |

Sin endpoint, API key o clave de seudónimo, el pipeline no se activa aunque el
flag sea `true`
(fail-closed de configuración, a diferencia del fail-open de ejecución).

## Componentes

- `src/observability/masking.py` — detectores y enmascarador, sin Agno.
- `src/observability/phoenix_export.py` — `SpanExporter` envolvente (allowlist +
  máscara + fail-closed) y alta del provider.
- Captura manual: spans creados por nuestro código en el adaptador de `LLMAccess`,
  con procedencia explícita por fragmento; documentos, extracciones y voz se
  excluyen antes de crear el span y un historial mixto se descarta entero.
- Documentación: `docs/production-security-privacy.md` (inventario de datos,
  retención, DPIA), `AGENTS.md` principio 11 (enmienda acotada) y ADR-006 punto 7.

## Diseño de captura (T6, decisión del propietario 2026-10-23)

Investigación de solo lectura sobre el código actual:

- `LLMAccess.model_for` lo usan el Agent principal, la extracción de documentos,
  Dream, la compactación de contexto y los evals. Varias de esas rutas reciben
  contenido documental o de memoria por diseño.
- En `GovernedModelMixin.ainvoke` los mensajes llegan ya mezclados (instrucciones,
  historial, resultados de tools, mensaje del usuario) y sin procedencia.
- Una transcripción de voz sustituye a `input_text` en el procesador
  (`voice_text`) y desde ahí no se distingue de texto escrito.

Por tanto **no se captura en `ainvoke`**. Se captura en
`GovernedInteractionRunner.run`, donde la procedencia se conoce por construcción:

**Lista de entrada por procedencia (allowlist):**

| Se captura (enmascarado) | Condición |
| --- | --- |
| Texto escrito del usuario | solo si no proviene de voz (`voice_text is None`) |
| Respuesta final (`present_reply`) | salida del modelo; solo si el turno cumple la excepción de abajo |
| Argumentos de las tools `propose_*` | enmascarado por esquema + patrón; misma condición |
| Metadatos por llamada al modelo | tokens, latencia, ruta, coste del ledger; sin texto |

**Excluido siempre, antes de crear el span:** transcripciones y audio; bloque de
adjuntos; resultados de tools de lectura (`untrusted_results`); historial y
resumen de compactación; y las rutas de extracción documental, Dream, compactación
y evals (no generan spans con contenido).

**Reglas:**

- **Excepción para contenido generado por el modelo (decisión del propietario,
  2026-10-25).** La respuesta final y los argumentos `propose_*` pueden reproducir
  contenido documental o de terceros que el modelo vio en el turno. Por eso solo se
  capturan si el turno no tuvo adjuntos y todas sus tools son `present_reply`,
  `propose_*` (salvo `propose_document_delete`, que nombra un documento) o una de la
  lista `SAFE_READ_TOOLS` (`src/observability/phoenix_capture.py`: `search_notes`,
  `list_todo_lists`, `list_todo_items`, `list_reminders`, `check_calendar`,
  `list_pending_proposals`, `find_vehicle`, `get_vehicle_summary`,
  `get_vehicle_maintenance_history`; confirmada por el propietario). En un turno que
  use `get_document`, `search_documents`, `search_documents_semantically`,
  `analyze_document`, `export_document`, `search_web`, o cualquier tool no
  clasificada, solo se guardan el texto escrito del usuario y los metadatos. El
  texto del usuario basta para saber qué se pidió; el contenido devuelto no se
  copia. Regla de fallo seguro: una tool nueva queda excluida hasta que se
  clasifique explícitamente.
- Sin etiquetado heurístico: si la procedencia no se conoce por construcción, no
  se captura. No se intenta adivinar si un fragmento «parece» un documento.
- El historial mixto se excluye entero.
- Coste: atributo desde el ledger (`_governed_record`), no cálculo de Phoenix.
- La voz queda **excluida de las trazas** por decisión del propietario; incluirla
  exigiría su propio análisis (BL-26: consentimiento y retención).

**Visibilidad por tool (decisión del propietario, 2026-10-25, opción A).** Cada
llamada a una tool genera un span `tool_metadata` hijo del turno, en orden de
llamada, con solo: nombre, posición, resultado `ok`/`error`, duración en ms y
tamaño del resultado en caracteres. Nunca argumentos de lectura, resultados ni
mensajes de error. Se emite también en los turnos que excluyen el contenido del
modelo, de modo que una llamada a `get_document` es visible aunque lo que
devolvió no lo sea. El nombre lo elige el modelo, así que solo se exporta si está
en el registro de tools conocidas (`KNOWN_TOOLS`); cualquier otro aparece como
`unknown_tool`, y un `propose_*` inventado no desbloquea contenido. Un test falla
si se define una `propose_*` nueva sin clasificarla en `PROPOSE_TOOLS`.
`list_my_preferences` y `propose_preference_forget` (Dream, no cableadas hoy en
`main.py`) están clasificadas; la primera queda como tool de contenido, fuera de
`SAFE_READ_TOOLS`, a la espera de decisión.

**Consecuencia aceptada:** las trazas muestran el mensaje, la respuesta final, qué
tools se llamaron con su resultado ok/error y duración, y los argumentos de las
propuestas, pero no lo que devolvieron las tools de lectura ni el historial.
Ver el dato concreto que devolvió una tool (opción B) exigiría decisión y
anotación en el inventario de privacidad aparte. Para un fallo como `InvalidPresentationOutputError`
se ve la entrada y el fallo, no el contexto completo que vio el modelo. Ampliar la
captura se decide fuente a fuente, cada una con su análisis.

## Criterios de aceptación

1. Con el flag en `false` no se crea provider, exporter ni conexión.
2. Con el flag en `true` y Phoenix caído, el Agent responde igual y no se
   acumulan reintentos ni bloqueos.
3. Ningún valor canario sensible (DNI, NIE, tarjeta, IBAN, matrícula, VIN, email,
   teléfono, token) llega al exporter real en el corpus sintético.
4. Si el enmascarador lanza excepción, el span no se exporta.
5. El pipeline de Grafana no recibe ningún atributo con contenido (test de
   privacidad sobre el exporter del Collector).
6. Audio, adjuntos y contenido de documentos no aparecen en ningún span.
7. Sin endpoint, API key o clave de seudónimo, el pipeline no se activa aunque
   el flag sea `true`.
8. Cada traza es localizable desde `telegram_interactions`/`llm_usage_events` por
   `correlation_id`.
9. El enmascarado no altera lo enviado al LLM ni lo persistido en PostgreSQL.
10. Falsos positivos medidos sobre texto cotidiano en español y documentados.
11. Ruff, mypy y suites unitaria e integración pasan.

## Riesgos y límites

- Enmascarar no es anonimizar: la traza sigue siendo dato personal (GDPR).
  Nombres propios, direcciones y salud en texto libre **no** se detectan.
- Una nueva copia de datos personales en infraestructura propia: requiere
  actualizar inventario, retención y DPIA antes de activar.
- El instrumentor puede cambiar atributos entre versiones: fijar versión y
  cubrir con test de contrato.
- Cambia el principio 11 solo para este pipeline; si la enmienda no se acepta, la
  spec no se implementa.

## Gate de activación en producción

Flag a `true` solo tras: spike cerrado, ADR-007 *Accepted*, criterios 1–11
verdes, documentación de privacidad actualizada, términos del piloto
(`docs/` de pilot terms) que mencionen la copia enmascarada de mensajes y la
retención de 30 días, y primera verificación E2E con el propietario. Despliegue manual y comprobación de SHA/CI como en AGENTS.md §10.
