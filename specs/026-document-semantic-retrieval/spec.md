# Spec 026 — Recuperación semántica de documentos

> **Status:** Implementado y validado E2E en producción.
> **Fecha:** 2026-10-04
> **Backlog:** BL-42

## Objetivo

Permitir que una persona encuentre documentos archivados mediante descripciones
en lenguaje natural —por ejemplo, “el contrato de alquiler de Murcia”— sin
convertir contenido documental en instrucciones ni romper el aislamiento por
tenant.

## Decisiones

1. PostgreSQL sigue siendo el almacenamiento canónico. Se habilita `pgvector`;
   no se introduce una base vectorial externa.
2. La primera versión indexa un único fragmento determinista y limitado por
   documento: filename, MIME y campos permitidos de la última extracción
   (`document_type`, `title`, `summary`, `entities`, `dates`, `amounts`). No
   persiste texto completo ni previsualizaciones transitorias del PDF.
3. La generación inicial usa 1536 dimensiones y `text-embedding-3-small` en
   desarrollo directo. Con Gateway, usa la ruta lógica
   `ancoramind-embeddings` → alias versionado `ancoramind-embeddings-r1`, que
   resuelve a `openrouter/openai/text-embedding-3-small`. Así el modelo físico,
   gasto y límites quedan centralizados con las demás rutas OpenRouter.
4. Cambiar de modelo o dimensión no modifica filas existentes: una nueva
   combinación `embedding_model` + `embedding_dimensions` crea/actualiza su
   propia versión del fragmento. La reindexación es explícita y posterior.
5. La ingesta de documentos es tolerante a fallos: el archivo y su extracción
   se archivan aunque el embedding falle. Se conserva una fila `failed` con
   clase de error acotada para reintento operativo futuro.
6. No hay reintentos automáticos ni fallback de proveedor. El Gateway sigue
   fail-closed; su alias debe añadirse a la virtual key con el script existente.

## Modelo de datos

`ancora.document_search_chunks` contiene `document_id`, `user_id`, referencia
opcional a extracción, índice de fragmento, hash/texto indexable, embedding,
proveedor/modelo/dimensión y estado. `document_id` tiene `ON DELETE CASCADE`;
la eliminación gobernada del documento elimina el índice vectorial asociado.

Toda consulta vectorial requiere simultáneamente `c.user_id = :user_id` y
`d.user_id = :user_id`, además de modelo/dimensión/estado completado.

## Seguridad y privacidad

- Datos recuperados se devuelven mediante el envelope `trust: untrusted_data`.
- Los embeddings, texto indexable, query del usuario y contenido documental no
  se envían a logs, spans ni métricas.
- El Core depende de `DocumentEmbeddingPort`; el adaptador físico es
  infraestructura y usa el Gateway/OpenAI-compatible configurado.
- La similitud es una señal de recuperación, no una autorización ni una fuente
  de instrucciones.

## Criterios de aceptación

1. `search_documents` conserva semántica de filename; la nueva capability es
   `search_documents_semantically`.
2. Un resultado semántico de otro usuario nunca puede aparecer.
3. Un fallo de embedding no revierte la ingesta.
4. La eliminación de documento elimina sus chunks por cascade.
5. La migración crea `vector`, tabla e índices y `init.sql` permanece alineado.
6. Ruff, mypy, unit tests y las integration tests de PostgreSQL pasan.

## Verificación operativa — 2026-10-15

- Se sincronizó el `gateway/litellm-config.yaml` versionado con
  `LITELLM_CONFIG_YAML` del servicio privado LiteLLM. Deployment Railway
  `bf1c29d3-2332-4868-bd25-782bbbf095eb`: `SUCCESS`, una réplica online y
  readiness superado.
- El alias base `ancoramind-embeddings-r1` quedó cargado con
  `openrouter/openai/text-embedding-3-small`. No se publicó ni mutó mediante
  `/model/new`.
- La virtual key existente se amplió de forma aditiva: el alias quedó autorizado
  y se verificó que todos los permisos anteriores permanecían presentes. No se
  recreó la key ni se expusieron secretos.
- Runtime config: revisión 6 válida y activada por CAS desde la 5, actor
  `operator:bl42-rollout`. La ruta lógica `ancoramind-embeddings` tiene capability
  `embeddings` y apunta a `ancoramind-embeddings-r1`.
- Tras aprobación explícita del coste se ejecutó una única inferencia con texto
  sintético no personal: `POST /v1/embeddings` → HTTP 200, alias efectivo
  `ancoramind-embeddings-r1`, 1536 dimensiones, 815 ms, UTC
  `2026-10-15T21:03:56.641078+00:00`. Railway corroboró el 200 a las
  `2026-10-15T21:03:56.656247383Z`. No hubo retry, fallback ni exposición del
  vector o payload.
- Este smoke cerró la ruta Gateway. La recuperación funcional se validó después
  mediante la reindexación explícita descrita a continuación.

### E2E funcional y aislamiento — 2026-10-15

- Se añadió `DocumentService.reindex_document_for_semantic_retrieval` como
  primitiva operativa explícita, no registrada como tool del Agent. Revalida la
  propiedad con `UserContext`, reutiliza el documento y su última extracción y
  no vuelve a leer el archivo ni repite extracción.
- El script metadata-only `scripts/document_semantic_e2e.py` ejecutó las tres
  llamadas aprobadas: reindexación del documento cuya ingesta sobrevivió al
  fallo inicial, búsqueda como propietario y la misma búsqueda como no
  propietario sintético. Resultado: `e2e_ok=true`, `reindex_ok=true`,
  `owner_search_found=true`, `non_owner_isolated=true`, modelo
  `ancoramind-embeddings-r1`, 1536 dimensiones y 2603 ms totales.
- Railway corroboró exactamente tres `POST /v1/embeddings → 200` entre
  `2026-10-15T21:40:38.776363236Z` y `2026-10-15T21:40:40.139861975Z`.
  Los logs de la app no contienen coincidencias de texto indexable, query o
  payload; no se imprimieron vectores, nombres, IDs ni secretos.
- PostgreSQL confirma una fila `completed` con vector de 1536 dimensiones y
  `error_class=NULL`. La fila histórica `failed/EmbeddingRouteUnavailable`
  permanece como auditoría de la combinación anterior `model=unavailable`, tal
  como exige el diseño versionado: reindexar con otro modelo crea su propia
  versión y no reescribe el fallo previo.
- Código desplegado: `b23087137a1431ae210b3ad868d5e4b185b48457`, deployment
  Railway `019b48a3-e9f1-470c-8e71-2ac66b217127` `SUCCESS`, entorno healthy.
  CI del mismo SHA: quality, integration y collector-config en verde.
