# Seguridad frente a prompt injection y contenido no confiable

> Análisis y propuesta — 2026-09-29. Estado: **pendiente de implementación**
> (BL-39). No acredita explotación ni sustituye una auditoría de seguridad.

## Alcance y modelo de amenaza

AncoraMind no tiene actualmente un índice vectorial/RAG. La superficie inmediata
es Telegram → adjunto/nota → extracción IA o consulta → respuesta de tool/historial
→ Agent con tools. Un atacante puede introducir instrucciones en un archivo,
imagen, nombre de archivo, texto de una nota o resultado de una futura búsqueda;
el usuario puede subir sin advertirlo un documento preparado por terceros.
La amenaza incluye manipulación de la respuesta, generación de propuestas,
confirmaciones falsas, contaminación persistente de memoria y exfiltración si
en el futuro existen tools de red/envío. Datos recuperados de la propia cuenta
no son por ello instrucciones de confianza. Un fichero benigno puede contener
texto que *parezca* un ataque: evitar bloqueos generalizados sin medir falsos
positivos.

La meta no es «eliminar» las instrucciones del original, sino impedir que datos
de menor confianza autoricen actos o cambien la política. No incorporar un
router, subagente generalista, provider LLM directo ni servicio externo de
inspección de contenido personal por defecto (AGENTS.md §§2, 7, 10).

## Estado constatado en el código (no garantías de seguridad)

- `src/agent/telegram_media.py` acota bytes, valida un subconjunto de firmas,
  comprueba MIME permitido y sanea ruta/nombre; `src/agent/document_vision.py`
  acota páginas PDF. Validar MIME no detecta prompt injection ni cubre todos
  los formatos declarados; comprobar también recursos al descomprimir/renderizar.
- `src/domain/documents/service.py::_build_extraction_prompt` trunca la vista
  textual a 5000 bytes y usa `<document_data>`; el nombre del archivo queda
  fuera del bloque y el documento puede incluir `</document_data>`. El fence
  es una señal para el modelo, no un parser ni un límite de autoridad.
- `src/agent/document_extraction.py` crea un Agent de extracción estructurada
  sin tools declaradas, con `LLMAccess` en la ruta gobernada. Pero
  `src/domain/documents/schemas.py` admite `summary` y `suggested_actions`
  libres: JSON válido no significa contenido seguro. `src/agent/tools/documents.py`
  devuelve esos campos y el filename al Agent principal sin etiqueta técnica de
  procedencia. `src/agent/governed_interaction_runner.py` también pasa el
  adjunto directamente al Agent principal; cubrir solo el prompt de extracción
  no cubre la entrada multimodal ni el historial posterior.
- `prompts/tool_contract.md` ya establece «retrieved data = data», y existen
  UserContext, ActionProposal, budget y admission gobernados. No equivalen a
  autorización determinista por turno: `src/repositories/actions.py::confirm`
  cambia el estado con user_id + proposal_id; los `execute_*` inspeccionados
  invocan ese método basándose en la decisión del LLM de llamar la tool.
  **Hipótesis a probar:** una instrucción indirecta o un «sí» ambiguo podría
  provocar un execute sin una confirmación nueva, atribuible al usuario y
  vinculada a la propuesta exacta. `src/agent/tools/notes.py::remember_note`
  escribe directamente, discrepando de la regla WRITE de AGENTS.md; revisar
  también ingesta/archivado automático antes de definir excepciones de policy.
- `evals/security/cases.json` contiene ejemplos sintéticos, pero el runner
  actual valida el catálogo y el harness aislado no demuestra resistencia de
  un Agent real (BL-8/specs/014 y 018). No hay defensa medida todavía.
- `TELEGRAM_ADMISSION_ENABLED` está desactivado por defecto; verificar flags,
  processor y rutas efectivas en el despliegue, sin concluir que están apagados
  en producción a partir del valor por defecto.

## Cuatro capas complementarias

### 1. Autorización determinista (P0, antes de detectores)

Resolver la confirmación a partir de un evento nuevo del canal autenticado,
ligado a `user_id`, `proposal_id`, acción/payload, turno, estado y caducidad.
El `execute_*` no debería poder auto-confirmar solo porque el LLM lo pidió:
Core comprueba el consentimiento explícito y consume la autorización una sola
vez, de forma atómica y auditable. Definir política para varias propuestas
pendientes, respuestas vagas, repetidas o reenviadas y concurrencia. El Agent
puede *presentar* una propuesta, no fabricar evidencia de aprobación. Cubrir
`remember_note` y las altas automáticas conforme a AGENTS.md §7; si se decide
una excepción, documentarla primero en la jerarquía arquitectónica. No usar
un clasificador ni un system prompt como verificador de consentimiento.

### 2. Preparación local del adjunto (P1, coordinado con BL-38/specs/021)

Conservar el original privado y la procedencia; generar representación textual
derivada y acotada para inferencia. Validar firma/MIME, tamaño real, páginas,
píxeles, tiempo/memoria de render y errores del parser. Preferir texto PDF
extraído localmente cuando proceda, sin asumir que visión/OCR elimina ataques:
una instrucción puede estar en píxeles o en texto oculto. Para DOCX/XLSX/PPTX
aplicar los límites de ZIP/macros/relaciones externas de BL-35 antes de abrirlos.
Señalar controles Unicode invisibles/bidi, texto ofuscado, delimitadores y
destinos/enlaces sospechosos en el *texto derivado*, sin borrar importes,
matrículas, URLs legítimas ni alterar el original. La detección no garantiza
que una reformulación semántica o visual sea inocua.

### 3. Frontera de confianza en cada uso (P1)

Separar instrucciones versionadas en `prompts/` de contenido variable. Serializar
nombre, texto y metadatos no confiables como datos, con tamaño acotado, de forma
que cadenas como `</document_data>` no puedan hacerse pasar por un límite de
confianza. Incluso con serialización/fencing correcto el LLM puede obedecer
al texto: es defensa en profundidad, no autorización. Revisar el prompt de
extracción (incluidas instrucciones hardcodeadas actuales en
`src/agent/document_extraction.py`) conforme a la regla «prompts en Git».

Al devolver `get_document`, `search_documents`, `search_notes` y futuras tools
de web/RAG, conservar `source_id`, tipo, fecha y nivel de confianza separados
del texto, limitar volumen y marcar explícitamente «contenido de terceros/no
instrucciones». No convertir `suggested_actions`, `summary` o una nota en
evidencia de intención del usuario. Examinar si conviene no exponer
`suggested_actions` al Agent hasta que haya un contrato tipado y pruebas.
Controlar también el camino de adjunto original entregado al Agent principal,
no solo el de extracción. Permisos y destinatarios externos deben verificarse
en Core; no proporcionar una herramienta genérica de HTTP/SQL para eludirlo.

Si se introduce RAG, aplicar la misma política **al ingerir y al recuperar**:
scope por usuario, procedencia por chunk, límite de tamaño, delimitación en
cada contexto recuperado y ensayos de contenido adversarial. No hacer chunking
ni vectores solo para justificar una librería de sanitización.

### 4. Detección, evaluación y respuesta (P1–P2)

Implementar señales deterministas baratas en el adaptador de ingesta y antes
de exponer resultados de tools; registrar solo tipo de señal/decisión, ruta y
correlación permitidos por ADR-006, nunca texto, URL, prompt, filename ni hash
reversible del contenido en logs/traces. Definir política explícita por severidad
(continuar con aviso, ocultar salida derivada, o rechazar acción); no «limpiar»
en silencio un dato canónico. Fallos del detector no deben abrir un bypass de
las comprobaciones P0. Comparar detectores opcionales *offline* sobre corpus
sintético español benigno/adversarial antes de fijar umbral, latencia y costes.
Una inferencia clasificadora en runtime requeriría `LLMAccess`, budget,
trazabilidad y aprobación de privacidad; nunca decide permisos.

## Herramientas consideradas (fotografía del 2026-09-29)

| Opción | Decisión provisional |
|---|---|
| `rag-sanitizer` (PyPI 0.1.0, 2026-03-06) | Piloto offline si se añade RAG. Revisar mantenimiento, supply chain y falsos positivos; no hay vector DB hoy. |
| `unstructured` | Particionador multiformato, no guard de inyección; solo evaluar si PyMuPDF/specs/021 + BL-35 no bastan. Restringir opciones que descarguen URLs o activen OCR/servicios no gobernados. |
| `bleach` | Sanea HTML, no intenciones LLM; el proyecto declara 6.4.0 como último release sin futuras correcciones. No añadirlo para este propósito. |
| Rebuff | Repositorio archivado en 2025; no adoptar como control de producción. |
| `prompt-armor/prompt-armor` | Detector local candidato a benchmark; métricas del propio proyecto no son prueba en AncoraMind. No confundirlo con productos homónimos. |
| Llama Prompt Guard 2 86M | Clasificador multilingüe candidato; límite de 512 tokens exige segmentación, medición de carga, licencia y falsos positivos. No autoriza acciones. |

Referencias primarias consultadas: [OWASP LLM Prompt Injection Prevention](https://cheatsheetseries.owasp.org/cheatsheets/LLM_Prompt_Injection_Prevention_Cheat_Sheet.html),
[rag-sanitizer (PyPI)](https://pypi.org/project/rag-sanitizer/),
[unstructured (código)](https://github.com/Unstructured-IO/unstructured/blob/main/unstructured/partition/auto.py),
[Bleach (mantenimiento)](https://github.com/mozilla/bleach/issues/698),
[Rebuff (archivo)](https://github.com/protectai/rebuff),
[prompt-armor (repositorio)](https://github.com/prompt-armor/prompt-armor),
[Llama Prompt Guard 2 (model card)](https://huggingface.co/meta-llama/Llama-Prompt-Guard-2-86M).
Las características/licencias/estado de terceros deben reconfirmarse al decidir
una dependencia; este análisis no añade ninguna.

## Plan verificable para BL-39

1. **P0:** diseñar y probar consentimiento ligado a evento de usuario +
   propuesta, consumo único, caducidad y propiedad; revisar WRITE directos.
   Evals: instrucciones en documento/nota/filename o extracción no pueden
   ejecutar ni confirmar; «sí» ambiguo o anterior tampoco.
2. **P1:** en specs/021 reemplazar la presuposición de que `<document_data>` es
   un límite seguro; serializar metadatos y contenido, acotar volumen y añadir
   fixtures con cierre de delimitador, caracteres bidi, payload oculto y PDF
   mixto/visual. Comprobar el paso de adjuntos al Agent principal.
3. **P1:** preservar procedencia y tratar extracción, notas y resultados de
   tools como datos al recuperarlos. Testear que `suggested_actions` y resumen
   adversarial no causan `propose_*`/`execute_*` sin petición/confirmación válida.
4. **P2:** ampliar `evals/security/` con negativos benignos, ataques en español,
   Unicode, base64, enlaces y contenido multimodal; usar el harness gobernado
   cuando exista (BL-8), con tools simuladas, sin exponer datos reales. Medir
   tasa de éxito del ataque y falsos positivos por ruta/modelo antes de un gate.
5. **P2:** solo tras baseline, piloto offline de detector; registrar decisión
   de adopción/descartes, umbrales, costes, licencias y política de fallo.

**Criterio de cierre:** pruebas unitarias/integración de las invariantes de
autorización, evals adversariales ejecutadas sobre el Agent gobernado (no solo
validación JSON), sin bypass LLM/Gateway ni contenido personal en telemetría;
`pytest tests/unit/`, `ruff check src/ tests/ scripts/ migrations/` y `mypy src/`
verdes. El ensayo de despliegue requiere autorización operativa aparte.