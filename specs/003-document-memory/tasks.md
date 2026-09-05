# Tasks: 003 — Document Memory

> ⚠️ Especificación retroactiva: las tareas se completaron antes de documentarse
> (BL-9). Se reconstruyen a partir del código existente para completar el registro SDD.

## Task Breakdown

### T1: Storage abstraction
- [x] `src/storage/base.py` — Protocol `DocumentStorage` (store, get, delete, exists)
- [x] `StoredDocument` dataclass (storage_key, original_filename, mime_type, size_bytes)

### T2: Local filesystem storage
- [x] `src/storage/local.py` — `LocalFileSystemStorage`
- [x] Sharding por fecha: `{base_path}/{YY}/{MM}/{uuid12}.{ext}`
- [x] Path traversal protection en get/delete/exists
- [x] `DOCUMENT_STORAGE_PATH` configurable (default `./data/documents`)

### T3: Domain models
- [x] `src/domain/documents/models.py` — DocumentCreate, Document, AIExtractionCreate, AIExtraction, DocumentWithExtraction
- [x] `from_attributes=True` para rows de repositorio

### T4: Extraction schemas
- [x] `src/domain/documents/schemas.py` — `GenericDocumentExtraction` + `VehicleInvoiceExtraction`
- [x] Campos comunes: summary, suggested_actions, confidence (0.0–1.0)

### T5: Database
- [x] `ancora.documents` table + indexes (user_id, created_at DESC)
- [x] `ancora.ai_extractions` table (FK document_id CASCADE, extraction JSONB, confidence)

### T6: Repository
- [x] `src/repositories/documents.py` — DocumentsRepository
- [x] create, get_by_id, search (ILIKE + LIMIT 20), delete
- [x] create_extraction, get_latest_extraction, get_document_with_extraction
- [x] All queries parameterized (`text()` + bind params) and user-scoped

### T7: Domain service
- [x] `src/domain/documents/service.py` — DocumentService
- [x] `ingest()` — pipeline: store → register → extract (automático, sin confirmación)
- [x] `_extract()` — extracción con prompt versionado (EXTRACTION_PROMPT_VERSION = "1.0")
- [x] `_run_extraction()` — Agent con output_schema; fallo → None (graceful)
- [x] `get_document()`, `search_documents()`, `delete_document()` (borra DB + fichero)

### T8: Tool adapters
- [x] `src/agent/tools/documents.py` — search_documents, get_document, analyze_document
- [x] `analyze_document` procesa adjuntos de Telegram vía parámetro built-in `files`
- [x] Respuestas formateadas en español (emoji moderado, tamaño en KB)

### T9: App wiring
- [x] Tools registradas en `_init_domain_tools()` (main.py)

### T10: Tests
- [x] 16 unit tests (document_models, document_storage, extraction_schemas)
- [x] Storage: sharding, path traversal, round-trip store/get/delete/exists
- [x] Schemas: defaults, confidence bounds, extracción completa invoice
- [ ] Integration test con PostgreSQL real (común con BL-2)

## Verification

- [x] `pytest tests/unit/` → **68 passed** (16 de documentos)
- [x] Pipeline completo implementado (store → register → extract)
- [x] Extracción con output_schema estructurado y versionado
- [x] Queries user-scoped y parametrizados
- [x] Extracción fallida no rompe la ingesta
- [ ] E2E Telegram con documento real pendiente (BL-1)