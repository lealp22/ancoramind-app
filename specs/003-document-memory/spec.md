# Spec: 003 — Document Memory

> **Milestone:** M3 — Document Memory
> **Status:** implemented (especificación retroactiva — creada a posteriori del código, ver BL-9)
> **Target:** Ingesta de documentos → storage → registro canónico → extracción IA → consulta

---

## Requirement

El usuario envía documentos por Telegram (facturas, fotos, PDFs). AncoraMind debe
archivarlos de forma persistente, extraer información con IA y permitir
consultas posteriores, con trazabilidad completa (quién, cuándo, de qué fuente).

Capacidad: `analyze_document` / `search_documents` / `get_document`.

### Must Have

- Tablas `ancora.documents` + `ancora.ai_extractions` en PostgreSQL
- Storage abstraído tras Protocol `DocumentStorage` (store, get, delete, exists)
- Implementación POC `LocalFileSystemStorage` con sharding por fecha `{base}/{YY}/{MM}/{uuid}.{ext}`
- Tool `analyze_document` — pipeline automático: store → register → AI extract
- Tool `search_documents` — búsqueda por filename (ILIKE) o lista reciente
- Tool `get_document` — detalle con su última extracción IA
- Extracción con `output_schema` estructurado (Pydantic) — no free-text
- Trazabilidad en extracción: provider, model, prompt_version, schema_version, confidence
- Todos los queries user-scoped y parametrizados
- Contenido del documento = DATA, no INSTRUCTIONS (no cambia permisos ni prompts)

### Should Have

- Modelos Pydantic con validación (Document, AIExtraction, DocumentWithExtraction)
- Separación Repository → Service → Tool (domain sin lógica de Agno)
- Schemas de extracción por tipo: `GenericDocumentExtraction`, `VehicleInvoiceExtraction`
- Extracción fallida no rompe la ingesta (documento queda registrado, extraction=null)
- Path traversal protection en storage local

### Won't Have (this milestone)

- OCR/vision real — la extracción usa filename + metadata (pendiente: BL-6)
- Provenance WRITE: los documentos se registran automáticamente, sin ActionProposal
  (la ingesta es automática por canal; el WRITE canónico ocurre en M4/M5 con
  `source_document_id`)
- Storage en S3/MinIO (solo Protocol + implementación local)
- Búsqueda semántica dentro del contenido

---

## Success Criteria

1. Usuario envía documento por Telegram → almacenado en filesystem + registrado en
   `ancora.documents` + extracción IA en `ancora.ai_extractions`
2. `search_documents("factura")` → encuentra por filename, respuesta en español
3. `get_document(id)` → muestra metadata + resumen de la extracción con confidence
4. Usuario B no puede ver documentos de Usuario A (queries scoped por user_id)
5. Si la extracción IA falla → el documento queda archivado igualmente (degradation
   graceful), con extraction=null
6. Storage key no permite path traversal (`../` rechazado)
7. Extracción versionada: prompt_version y schema_version registrados por cada resultado

---

## Notas de implementación (retro)

- **Excepción arquitectónica aceptada:** `domain/documents/service.py` usa
  `agno.agent.Agent` con `output_schema` para la extracción — única incursión
  del runtime en domain (documentada en AGENTS.md §3, pendiente de abstraer si
  se cambia de framework).
- El modelo de extracción se instancia como `OpenAIChat(id="gpt-5.4-mini")` en
  el adaptador de tools (`agent/tools/documents.py`), no reutiliza la factory
  `create_model()` — mejora candidata.
- `VehicleInvoiceExtraction` se define aquí pero su consumo real llega con M4
  (mantenimiento vinculado a `source_document_id`).
