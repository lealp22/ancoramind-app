# Spec 022 — BL-39: frontera de confianza de datos LLM

> Estado: en curso, 2026-09-30. Dos incrementos locales; no validado con
> Telegram, PostgreSQL ni proveedor LLM real.

## Objetivo y prioridades

Un archivo, nombre, nota, extracción o resultado de tool es dato de menor
confianza, aunque lo suba el propio usuario. Ninguno debe autorizar operaciones
WRITE/EXTERNAL_ACTION/DESTRUCTIVE ni alterar las instrucciones del Agent. No
existe RAG actualmente. Véase `docs/llm-security-hardening.md`.

### P0 — consentimiento verificable (diseño acordado; no implementado)

Invariante: `execute_*` debe rechazar cualquier propuesta no autorizada mediante
un evento de usuario **posterior a la propuesta**, autenticado por el canal,
vinculado a `user_id`, `proposal_id` y al payload inmutable. El LLM no puede
generar la prueba de consentimiento ni inferirla de documentos, notas, outputs
de tools o historial anterior. El Core debe consumirla una sola vez; replay,
concurrencia, cambios de payload, cross-user y propuesta expirada no ejecutan.
Múltiples propuestas abiertas requieren referencia inequívoca; «Sí» ambiguo
debe pedir aclaración. El canal/transporte no se presupone Telegram dentro de
`domain/`; el adaptador de Telegram obtiene la identidad/turno del ledger.

Diseño de UX, TTL, procedencia, estados, transacciones y tratamiento de fallo
ambiguo: `consent-design.md`. Incluye inventario de todos los `execute_*`,
`remember_note` y la ingesta automática, y bloqueo de la ruta AgentOS legado
sin evidencia equivalente. **Implementado y validado con PostgreSQL real
(2026-10-02, `specs/023-audit-remediation` T4.1–T4.8)**, detrás de
`GOVERNED_CONSENT_ENABLED` (apagado por defecto en producción — ver
`verification.md` §"P0 — implementado"). No aplicar un guard solo a una
tool dejando las demás abiertas, ni considerar un `prompt` de confirmación
como control. Toda excepción a AGENTS.md requiere aprobación y reflejo en
`docs/architecture.md`.

### P1 — frontera documental (primer incremento local)

- Mover las instrucciones de extracción al asset versionado
  `prompts/skills/document_extraction.md`. La extracción continúa por
  `DocumentExtractionPort`/`LLMAccess`; no añadir providers ni red.
- Serializar metadatos y vista textual truncada en un objeto JSON `source`
  junto con `target_schema`; no concatenar filename fuera de `source` ni usar
  `</document_data>` como límite. Escapar caracteres de markup y controles;
  preservar datos completos en almacenamiento canónico, sin mutar el original.
  Versionar el cambio como prompt de extracción 1.2 (schema 1.1 inalterado).
- No promover `suggested_actions` generado por IA en las respuestas de
  `analyze_document` / `get_document`; el campo permanece en la extracción
  persistida para compatibilidad, pero no es señal de intención del usuario.
- Probar localmente contenido adversarial con cierre falso, filename multilínea,
  Unicode y truncado, además de regresión de la ruta visual/binaria. La
  serialización JSON reduce confusión sintáctica, **no prueba** que el modelo ignore una
  instrucción en el documento; las comprobaciones de permiso son independientes.

### P1 — lectura de notas y documentos (segundo incremento local)

- `search_notes`, `search_documents` y `get_document` presentan registros en
  un sobre JSON con `trust: untrusted_data`, `source`, `total_matches`,
  `records_omitted` y `records`. Cada registro marca su origen (nota/documento
  canónico); el resumen de extracción se marca `ai_extraction_unverified`.
- Solo la representación para el Agent se acota: máximo 10 registros por
  respuesta, 1200 caracteres por nota/resumen y 255 por filename/tipo extraído.
  Cada campo recortado incluye su indicador `_truncated`. Se conservan ID,
  fecha, tamaño y confianza para consultas posteriores. La búsqueda subyacente
  sigue limitada a 20 registros por repositorio: `total_matches` indica solo
  el tamaño de la página devuelta, **no** el número global en DB.
- Se serializan y escapan saltos de línea, Unicode, caracteres de markup y
  cierres falsos dentro de campos JSON. Ni la query ni un ID inválido se
  interpolan en mensajes de error. No se modifica el dato persistido, la
  autorización ni el retorno de `analyze_document` (que requiere revisión
  separada). Esto **no** impide que un modelo obedezca instrucciones semánticas.
- El contrato de tool en `prompts/tool_contract.md` explicita que notas y
  resultados recuperados son datos y no prueban confirmación; la instrucción
  vive en el asset versionado, no en un string de runtime.

### P1/P2 — siguientes incrementos

- Extender procedencia/acotación al resto de resultados de tools; revisar el
  adjunto que `GovernedInteractionRunner` pasa directamente al Agent (también
  la ruta AgentOS legado). No afirmar que este incremento protege esas superficies.
- Coordinar BL-38/specs/021 antes de exponer texto PDF adicional; BL-35 para
  límites de formatos ofimáticos. Evitar telemetría con contenido (ADR-006).
- En BL-8/specs/018: corpus sintético ampliado (8 casos nuevos). Pendiente
  conectar harness a Agent gobernado con tools simuladas, medir falsos positivos
  y eficacia antes de adoptar detectores. Nunca activar clasificación pagada
  ni despliegue remoto como parte de la validación local.

## Criterios de aceptación locales

1. Texto y filename adversariales siguen siendo campos JSON y se recuperan
   intactos mediante parser; la serialización no contiene un cierre literal
   `</document_data>` ni salto de línea inyectado fuera de una cadena.
2. PDFs sin páginas preparadas no se anuncian como imágenes adjuntas; la ruta
   con páginas sí se declara, sin persistirlas ni registrarlas en logs.
3. Las dos tools documentales omiten `suggested_actions` incluso si la
   extracción lo contiene, pero conservan el resumen factual.
4. Tests unitarios, Ruff, mypy y catálogo evals pasan sin infraestructura.
   Estas pruebas NO satisfacen la aceptación P0 ni prueban resistencia de un
   Agent LLM real: BL-39 sigue abierto.
5. Lecturas simuladas mantienen información útil y procedencia, limitan la
   salida, preservan datos canónicos y no permiten que saltos, cierres falsos
   o caracteres Unicode rompan la representación; corpus sintético ampliado
   con ataques y controles benignos (solo validación estática).