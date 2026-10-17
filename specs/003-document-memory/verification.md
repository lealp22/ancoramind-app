# Verification: 003 — Document Memory

## E2E visual autorizado — 2026-10-17

**PDF raster sintético PASS; PNG parcial (consulta de fecha, BL-50).**
Un envío por formato, más una consulta conjunta posterior por Telegram:

- Dos originales conservados en Storage y cotejados por SHA-256 con fixtures
  y filas canónicas. PDF de una página sólo imagen, sin texto embebido.
- Dos extracciones estructuradas por `ancoramind-vision-r1` ya activo,
  revisión 8, sin habilitar rutas ni desplegar. Referencias/fechas/cantidades
  extraídas correctamente; precio/total del PDF también correctos.
- Respuestas con procedencia y advertencia de extracción automática; consulta
  posterior devuelve nombres/IDs correctos sin nueva llamada visual.
- Fecha del PNG persistida pero ausente en la respuesta inicial y posterior:
  `_extraction_record` transmite sólo tipo/resumen/confianza, omitiendo campos
  estructurados. Reproducido con la extracción real, sin corregir producto.
- Dos documentos/dos extracciones al final, índices de búsqueda completados,
  cero propuestas. No prueba de aislamiento real con segunda cuenta.
- Coste **parcial**: 0,00946220 USD de conversación estimados; visión sin
  coste informado y embeddings fuera de contadores/ledger LLM actuales (BL-51).
  No es un total ni un benchmark de coste; no repetir inferencia para completarlo.
- 53 unitarias focales, 1504 unitarias globales y 7 integraciones documentales
  en PostgreSQL local `_test` superadas. Cambios de esta entrega sólo docs.

Evidencia/IDs/hashes/limitaciones:
`specs/008-railway-deployment/mvp-release-campaign.md`, entrega 4.
Lo que sigue conserva el registro histórico de verificaciones anteriores.

> Especificación retroactiva (BL-9). Verificación reconstruida a partir del
> código y los tests existentes. El E2E de PDF textual y su consulta de
> seguimiento se validó en Telegram/Railway el 2026-10-13; los demás E2E de
> BL-1 permanecen pendientes.
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

### E2E-003-001: Ingesta y consulta (parcialmente validado — 2026-10-13)

```text
User: [envía un PDF real con capa de texto por Telegram]
Processor: claim atómico → descarga validada → ingesta/preparación documental
           antes del Agent → persistencia canónica
Agent: ✅ Documento archivado + resumen correcto (confianza aproximada 85 %)

User: [formula una pregunta de seguimiento sobre la documentación del PDF]
Agent: respuesta correcta basada en la guía archivada, con aviso de confianza.
```

La evidencia se obtuvo en Railway el 2026-10-13. El PDF original no se entregó
al Agent mediante `files=`/`images=`: el turno sólo recibió el resumen canónico
acotado como `untrusted_data`. No se observó el error anterior de parser/rate
limit de OpenRouter. Queda pendiente comprobar la búsqueda/lectura explícita por
`search_documents`/`get_document`, el aislamiento entre usuarios y la ruta
visual de imágenes/PDF escaneados.

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
- [x] E2E Telegram con PDF textual real y consulta de seguimiento (Railway,
      2026-10-13); pendientes búsqueda/lectura explícita y ruta visual.
- [x] Integration tests con PostgreSQL real: 155 passed, 1 skipped
      (2026-10-13).