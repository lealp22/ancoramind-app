# Verification: 003 — Document Memory

> Especificación retroactiva (BL-9). Verificación reconstruida a partir del
> código y los tests existentes. Los E2E manuales quedan pendientes (BL-1).
> Actualización 2026-09-20: el flujo gobernado conserva referencias de media
> cifradas y procesa imágenes/PDF tras el claim; la validación Railway con
> credenciales reales sigue pendiente.

## Automated Tests

### Unit Tests (16 of 68 total passing)

| Test file | Tests |
|---|---|
| `test_document_models.py` | DocumentCreate, Document from_attributes, AIExtractionCreate, DocumentWithExtraction |
| `test_document_storage.py` | Protocol, LocalFileSystemStorage: store con sharding, get, delete, exists, path traversal rechazado |
| `test_extraction_schemas.py` | GenericDocumentExtraction defaults, confidence bounds, VehicleInvoiceExtraction completo |

### Key Behaviors Verified

```
test storage path traversal:
    → storage_key con "../" rechazado (ValueError / False)

test extraction graceful failure:
    → _run_extraction devuelve None si el modelo falla;
      el documento queda registrado con extraction=null

test confidence bounds:
    → confidence fuera de [0.0, 1.0] rechazado por Pydantic
```

## Manual E2E Tests (pendiente — requiere credenciales reales + PostgreSQL)

### E2E-003-001: Ingesta y consulta (por hacer — BL-1)
```
User: [envía factura_taller.pdf por Telegram]
Processor: claim atómico → descarga validada → analyze_document(run_context, files=[...])
Agent: 📄 factura_taller.pdf recibido y archivado. ID: `...`
       + resumen de extracción visual Qwen (máximo 3 páginas PNG renderizadas)

User: Busca la factura del taller
Agent calls: search_documents(run_context, query="taller")
Agent: Encontré 1 documento(s) sobre "taller": ...

User: [pide detalle por ID]
Agent calls: get_document(run_context, document_id="...")
Agent: ficha completa + extracción con confidence
```

### E2E-003-002: Aislamiento entre usuarios (por hacer — BL-1)
```
User B: Busca la factura
→ search_documents NO devuelve documentos de User A
```

## Acceptance Criteria

- [x] 16 unit tests de documentos pasan (68 total)
- [x] Storage tras Protocol; LocalFileSystemStorage con sharding por fecha
- [x] Path traversal protection
- [x] Tablas `documents` + `ai_extractions` con FK CASCADE e indexes
- [x] Queries parametrizados (text() + bind params) y user-scoped
- [x] Pipeline automático sin ActionProposal (ingesta por canal; el WRITE
      canónico con `source_document_id` ocurre en M4/M5)
- [x] Extracción versionada (prompt_version + schema_version + provider + model)
- [x] Extracción fallida → degradación graceful
- [x] Referencias de media Telegram cifradas; descarga tras claim atómico
- [x] Límite de tamaño/MIME aplicado antes de persistir/inferir
- [x] Imágenes y páginas PDF transitorias pasan por ruta lógica gobernada `ancoramind-vision`
- [ ] E2E Telegram con documento real (BL-1)
- [ ] Integration tests con PostgreSQL real (BL-2)