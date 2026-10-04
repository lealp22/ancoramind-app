# Spec 026 — Recuperación semántica de documentos

> **Status:** Implemented locally — pendiente activar/publicar el alias de embeddings en el Gateway desplegado y validar E2E.
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
   `ancoramind-embeddings` → alias versionado `ancoramind-embeddings-r1`.
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