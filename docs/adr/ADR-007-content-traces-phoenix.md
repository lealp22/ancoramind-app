# ADR-007 — Trazas con contenido enmascarado en Phoenix

> **Status:** Accepted (2026-10-23, decisión del propietario) **como autorización
> para implementar detrás de flag OFF**. No autoriza activar la captura en
> producción: eso exige el gate de activación de specs/046.
> **Contexto:** hoy no se puede saber qué vio el modelo ni por qué falló una
> petición concreta. Grafana (ADR-006) es metadata-only por diseño.
> **Enmienda (en vigor):** modifica el principio 11 de `AGENTS.md` y el punto 7
> del ADR-006 solo para el pipeline de Phoenix. Grafana sigue sin contenido.

## Decisión de aceptación (2026-10-23)

El propietario decide guardar en Phoenix una copia **enmascarada** del contenido de
las conversaciones de todos los usuarios autorizados, con retención de 30 días, y
que la captura sea **manual**: el seam vive en el adaptador gobernado de
`LLMAccess`, con procedencia confiable del texto, y se excluyen documentos,
extracciones y voz **antes** de crear el span. La auto-instrumentación global de
Agno (`openinference-instrumentation-agno`) queda **descartada** como vía de
producción: no distingue la procedencia del texto. Un historial de procedencia
mixta se excluye entero.

---

## Contexto

PostgreSQL responde qué quedó registrado y Grafana cómo se ejecutó, pero ninguno
conserva el contenido de una petición. Un fallo como `InvalidPresentationOutputError`
solo deja un contador. El contenido ya viaja a OpenRouter; guardar una copia
enmascarada y con retención corta en infraestructura propia es un riesgo distinto,
no necesariamente mayor, y exige controles propios.

## Decisión

1. **Backend** — Arize Phoenix autoalojado en Railway (template Postgres + Phoenix),
   UI con autenticación y sin acceso público de lectura.
2. **Pipeline separado** — `TracerProvider` y exporter propios para Phoenix,
   independientes del pipeline de Grafana. Ningún atributo con contenido puede
   entrar en el Collector actual.
3. **Activación** — flag, desactivado por defecto, fail-open. Phoenix nunca es
   fuente de verdad ni bloquea Telegram, Core o inferencia.
4. **Correlación** — cada traza lleva `ancora.correlation_id` e `interaction_id`,
   para saltar desde `telegram_interactions`/`llm_usage_events` a la traza.
5. **Usuario seudonimizado** — se exporta un HMAC de `telegram_user_id`, nunca el ID.
6. **Retención corta** y borrado por usuario documentado (valor a fijar en la spec).

## Alcance de captura

### Excluido por construcción (nunca entra en un span)

- Audio y transcripciones brutas.
- Adjuntos y bytes de documentos.
- Contenido de documentos y extracciones IA (`ai_extractions`).
- Secretos, tokens, claves y cabeceras de autorización.

La exclusión se aplica con una **allowlist de atributos OpenInference** en el
exporter de Phoenix, no con una lista de bloqueo: lo no listado se descarta.

### Capturado y enmascarado

Mensaje del usuario, prompt enviado, respuesta del modelo y argumentos/resultados
de tools. Todo texto pasa por el enmascarador antes de exportarse.

## Enmascarado de datos sensibles

Se aplica **solo a la telemetría**. El modelo recibe el dato real, porque lo necesita
para actuar; el enmascarado nunca modifica lo que se envía al LLM ni a la BD.

Tres capas, de más a menos fiable:

1. **Por esquema (determinista).** Los argumentos de tools conocidas se enmascaran
   por nombre de campo, sea cual sea su formato: `registration`, `vin` y cualquier
   campo marcado como identificador en el modelo de dominio. Es la capa más fiable
   porque no depende de reconocer el formato.
2. **Por patrón con validación.** En texto libre, cada detector exige validar el
   checksum o el formato para reducir falsos positivos:

   | Dato | Validación |
   |---|---|
   | Tarjeta de crédito | 13–19 dígitos + Luhn, con espacios o guiones |
   | DNI / NIE | formato + letra de control (módulo 23) |
   | IBAN | país + longitud + módulo 97 |
   | Matrícula | formatos españoles actual (`1234 BCD`) y anteriores (`M-1234-AB`) |
   | Bastidor (VIN) | 17 caracteres sin I/O/Q |
   | Email, teléfono | patrones originados en `web_search`, ahora en `masking.py` |
   | Claves y tokens | prefijos conocidos y cadenas largas de alta entropía |

3. **Red de seguridad.** Secuencias numéricas largas no reconocidas se enmascaran
   por defecto.

Sustitución por marcador tipado (`[DNI]`, `[TARJETA]`, `[MATRICULA]`), sin conservar
dígitos. La correlación entre apariciones del mismo valor, si hiciera falta, usaría
un HMAC truncado con clave en secreto; se decide en la spec.

### Fail-closed

Si el enmascarador lanza una excepción o no puede procesar un span, **ese span no se
exporta**. Perder una traza es aceptable; exportar un dato sin enmascarar, no.

### Límites reconocidos

- Los patrones no detectan nombres propios, direcciones ni datos de salud en texto libre.
- **Enmascarar no es anonimizar.** La traza sigue siendo dato personal a efectos de
  GDPR: exige retención, control de acceso y supresión por usuario.
- Presidio u otro NER se evaluará solo si los patrones resultan insuficientes; su
  cobertura en español y su peso en el contenedor no están verificados.

## Implementación prevista

- Módulo `src/observability/masking.py` sin dependencias de Agno, reutilizable.
  Creado el 2026-10-21 (no requiere que este ADR esté aceptado). Expone
  `detect_sensitive`, `mask_sensitive` y `scan_sensitive`. Hoy `mask_sensitive`
  solo lo usan los tests; su consumidor previsto es el `SpanExporter`.
- **Búsqueda web (specs/025): rechaza, no enmascara.** `WebSearchService` ya usa
  `detect_sensitive` y, si hay coincidencia, rechaza la consulta
  (`sensitive_query`) sin llamar a Tavily. Enmascarar aquí enviaría una consulta
  sin sentido (`qué es [BASTIDOR]`) y gastaría un crédito para resultados
  irrelevantes. Son políticas distintas sobre los mismos detectores:
  - telemetría: enmascarar (el dato real sí llega al modelo y a la BD);
  - salida a terceros (búsqueda): rechazar (el dato no debe salir).

  Contrapartida aceptada: los falsos positivos (p. ej. un VIN público o una
  referencia larga) obligan a reformular. Cualquier cambio de los detectores
  afecta a ambos usos y debe revisarse contra los dos.
- Un `SpanExporter` envolvente que enmascara y aplica la allowlist antes de delegar.
- **Captura manual** (decisión 2026-10-23) en el adaptador gobernado de `LLMAccess`,
  con spans creados por nuestro código y procedencia explícita por fragmento de
  texto. No se usa `openinference-instrumentation-agno` en producción; el
  prototipo de `scripts/phoenix_spike/` es solo referencia.

## Pruebas exigidas antes de activar en producción

- Corpus sintético con DNI, NIE, tarjetas, IBAN, matrículas y VIN válidos e inválidos.
- Test de privacidad: ninguna canario sensible llega al exporter.
- Test de que el pipeline de Grafana no recibe ningún atributo con contenido.
- Test de fail-closed ante error del enmascarador.
- Medida de falsos positivos sobre texto cotidiano en español.

## Consecuencias

### Positivas

- Se puede reconstruir qué pasó en una petición concreta y por qué falló.
- El contenido sensible reconocible no sale del proceso sin enmascarar.
- Base común para los evals (specs/044) y el diagnóstico en producción.

### Negativas

- Nuevo servicio con Postgres propio y nueva copia de datos personales.
- El enmascarado por patrones es incompleto y requiere mantenimiento.
- Obliga a actualizar `docs/production-security-privacy.md` (inventario, retención, DPIA).

## Pendiente antes de activar en producción

- Spike sintético ejecutado (2026-10-22): compatibilidad Agno/terminal, provider
  separado, exporter experimental, auth y borrado local probados; límites en
  `specs/046-phoenix-masked-traces/spike-result.md`. Coste/UI y overhead aceptable
  no demostrados; sin inferencia real ni integración productiva.
- Diseñar e implementar el seam manual con procedencia confiable y su prueba de
  exclusión de documentos/transcripciones/voz (T6). Verificar primero qué
  distingue hoy `governed_model.py` entre texto de usuario y contenido documental.
- Retención 30 días y todos los usuarios autorizados decididos por el propietario
  (2026-10-20). Pendiente ejecución productiva de borrado paginado, privacidad,
  términos y control de acceso/red antes de activar.
- Medir latencia con export real en Railway y definir cómo se aporta el coste
  (atributo desde el ledger).
- Aceptación **de la activación** (flag ON) sigue siendo una decisión posterior.
