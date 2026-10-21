# ADR-007 — Trazas con contenido enmascarado en Phoenix

> **Status:** Proposed (borrador, sin implementación). Pasa a Accepted solo tras
> el spike de compatibilidad y la aprobación del propietario.
> **Contexto:** hoy no se puede saber qué vio el modelo ni por qué falló una
> petición concreta. Grafana (ADR-006) es metadata-only por diseño.
> **Enmienda:** al aceptarse, modifica el principio 11 de `AGENTS.md` y el punto 7
> del ADR-006 solo para el pipeline de Phoenix. Grafana sigue sin contenido.

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
- Instrumentación `openinference-instrumentation-agno` solo si el spike confirma
  compatibilidad con `agno>=2.9`, `present_reply` y `tool_choice=required`.

## Pruebas exigidas antes de aceptar

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

## Pendiente antes de aceptar

- Spike de compatibilidad del instrumentor y del cálculo de coste con aliases propios.
- Fijar retención, política de borrado y acceso a la UI.
- Decidir si el texto de usuarios distintos del propietario puede entrar.
