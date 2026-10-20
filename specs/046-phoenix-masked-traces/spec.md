# Spec 046 — Trazas con contenido enmascarado en Phoenix

Estado: propuesta, sin implementar. Desarrolla el ADR-007 (Proposed). Nada de
esta spec se implementa hasta cerrar el spike (`spike.md`) y que el propietario
acepte el ADR.

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
- Instrumentación Agno solo si el spike la valida; si no, spans manuales en el
  adaptador de `LLMAccess`.
- Documentación: `docs/production-security-privacy.md` (inventario de datos,
  retención, DPIA), `AGENTS.md` principio 11 (enmienda acotada) y ADR-006 punto 7.

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
