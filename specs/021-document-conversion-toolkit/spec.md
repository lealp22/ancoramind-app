# Spec: 021 — Document Conversion Toolkit (text-layer PDF/DOCX + Markdown export)

> **Backlog:** BL-38
> **Status:** draft (2026-09-29)
> **Target:** portar la lógica determinista de conversión de documentos del
> servidor MCP externo `mcp_doc_to_markdown.py` a `src/domain/documents/`,
> empezando por la detección de capa de texto en PDF (ahorro de coste directo
> sobre BL-6) y dejando preparado el terreno para DOCX (BL-35) y export
> Markdown→PDF (BL-29).

---

## Contexto

Existe un servidor MCP local, fuera de este repositorio
(`C:\Users\0020572\OneDrive - ViewNext\IA\Research\tools\mcp_doc_to_markdown.py`),
con conversores ya probados:

- `get_pdf_info`: detecta si un PDF tiene capa de texto extraíble
  (`page.get_text("text")` con PyMuPDF) o es escaneado.
- `convert_to_markdown`: PDF con texto → Markdown vía `pymupdf4llm`; DOCX →
  Markdown vía `mammoth`/`markdownify`.
- `convert_scanned_pdf_to_markdown`: PDF escaneado → Markdown por visión,
  página a página, con un cliente LLM físico directo.
- `convert_vtt_to_markdown`, `convert_markdown_to_docx`.

Ese servidor **no se conecta como infraestructura del runtime**: no pasa por
`LLMAccess`, no tiene `RuntimeConfigSnapshot`/budget/auditoría, y vive fuera
del repo (AGENTS.md §2.1/§2.9). Este spec porta solo la **lógica determinista**
reutilizable, detrás de los puertos ya existentes (`DocumentExtractionPort`,
BL-6/specs/013 T9), y acota el alcance a lo que puede cerrarse sin depender de
otro backlog en curso.

## Requirement

### Must Have

1. **Detección de capa de texto en PDF.** Antes de invocar la ruta visual
   (`ancoramind-vision`), comprobar con PyMuPDF si el PDF tiene texto
   extraíble. Si lo tiene, extraer con `pymupdf4llm` de forma determinista
   (cero coste de inferencia, cero budget); si no, seguir la ruta visual ya
   implementada (`prepare_visual_pages`). Este es el refinamiento ya anotado
   en BL-6 ("preferir extracción textual… reservar visión para escaneados").
2. **El Markdown extraído es DATA, nunca instrucciones** (AGENTS.md §2.8):
   entra en el mismo `<document_data>` delimitado que ya usa
   `DocumentService._build_extraction_prompt`, sujeto a los mismos límites de
   tamaño (`MAX_TEXT_PREVIEW_BYTES`) y al mismo pipeline de extracción
   estructurada (`GenericDocumentExtraction`).
3. **Sin provider físico nuevo.** La detección y la extracción determinista no
   crean ningún cliente LLM; sólo usan PyMuPDF/`pymupdf4llm` localmente. La
   ruta visual sigue intacta y sigue pasando por `AgnoDocumentExtractionAdapter`
   / `LLMAccess`.
4. **Límites de coste/tamaño explícitos** para la extracción determinista:
   número máximo de páginas procesadas y bytes máximos de texto extraído antes
   de truncar (reusar o alinear con `document_vision_max_pdf_pages` /
   `MAX_TEXT_PREVIEW_BYTES` donde aplique).
5. **Nueva dependencia `pymupdf4llm`** añadida a `pyproject.toml` sólo tras
   confirmar licencia y huella de instalación (PyMuPDF ya es dependencia
   directa; `pymupdf4llm` es una capa fina sobre ella).
6. Tests unit que demuestren: PDF con texto → ruta determinista sin llamar al
   extraction port de visión; PDF escaneado → sigue llamando a la ruta visual
   sin cambios de comportamiento; PDF con texto parcial (algunas páginas sin
   texto) → decisión documentada y probada.

### Should Have

- Registrar en la extracción persistida (`ai_extractions`) una señal
  metadata-only de qué ruta se usó (determinista vs. visual) para permitir el
  benchmark de precisión/coste que BL-6 tiene pendiente, sin añadir contenido
  ni prompts a la auditoría.

### Won't Have (este incremento)

- **DOCX determinista** (`mammoth`/`markdownify`): depende de BL-35 (ingesta
  ofimática, con sus propios límites de seguridad — macros, ZIP bombs, límites
  de profundidad). No se implementa aquí; queda como Fase 2 explícita en
  `tasks.md`, bloqueada por el cierre de BL-35.
- **Markdown → PDF (export de salidas del asistente)**: depende de BL-29
  (renderizado Telegram) y de decidir el mecanismo de generación (DOCX→PDF vía
  `markdown_docx_converter.py` + conversor, o HTML→PDF). Queda como Fase 3
  explícita en `tasks.md`, bloqueada por una decisión de diseño propia.
- `convert_vtt_to_markdown`: sin caso de uso real en AncoraMind hoy: no se
  implementa especulativamente.
- Sustituir o modificar `AgnoDocumentExtractionAdapter`, `LLMAccess` o la ruta
  visual: permanecen intactos.
- Cualquier cambio a `pdf_img_to_md.py` / cliente de visión directo del repo
  origen: no se porta ese cliente físico bajo ninguna circunstancia.

## Design

```text
analyze_document (tool)
  → prepare_visual_pages / prepare_text_pages (nuevo, src/agent/document_vision.py o módulo hermano)
       ├── PDF con texto extraíble → pymupdf4llm.to_markdown() → texto DATA
       │     → DocumentService._extract() SIN visual_pages (ruta determinista existente)
       └── PDF sin texto / imagen → visual_pages (sin cambios)
             → DocumentService._extract() CON visual_pages → ruta visual (sin cambios)
```

- **Punto de decisión único**: una función determinista
  `has_extractable_text(content: bytes) -> bool` (PyMuPDF, sin I/O externo)
  llamada desde `src/agent/tools/documents.py::analyze_document` antes de
  `prepare_visual_pages`, análoga a `get_pdf_info`/`likely_scanned` del origen.
- **Extracción de texto determinista**: nueva función
  `extract_pdf_text_markdown(content: bytes, *, max_pages: int) -> str` en
  `src/agent/document_vision.py` (o módulo nuevo junto a él, respetando que
  domain/ no importa librerías de bajo nivel de PDF directamente — esa lógica
  vive en la capa `agent/`, igual que `prepare_visual_pages` hoy).
- **`DocumentService` no cambia de contrato**: sigue recibiendo `content` y
  `visual_pages`; cuando la extracción es determinista, el texto ya extraído
  se inyecta en el prompt igual que hoy se inyecta `text_preview` para
  `text/*`, evitando tocar `_build_extraction_prompt` más de lo necesario
  (extender el criterio de "tiene texto" a PDFs con capa de texto detectada).
- **No se crea un nuevo puerto de dominio** para esto: es preprocesamiento de
  infraestructura (extracción de bytes → texto), no una inferencia gobernada;
  encaja en la misma capa que ya prepara `visual_pages`.

## Success Criteria

1. Un PDF con capa de texto sube por Telegram → `analyze_document` extrae con
   `pymupdf4llm` (cero llamadas al extraction port de visión) y persiste la
   extracción con el mismo pipeline de `ai_extractions`.
2. Un PDF escaneado (sin texto) sigue exactamente el mismo camino que hoy
   (ruta visual, `ancoramind-vision`) — cero regresión.
3. Un PDF con parte de sus páginas sin texto se comporta según lo decidido y
   documentado en `tasks.md` (todo-o-nada vs. mixto), con test que lo prueba.
4. `pytest tests/unit/` y `ruff check src/ tests/ scripts/ migrations/` en
   verde; `mypy src/` limpio.
5. `pyproject.toml` declara `pymupdf4llm` con versión mínima acorde a
   `PyMuPDF>=1.24.0,<2.0.0` ya fijado.
6. BACKLOG.md BL-38 y BL-6 actualizados referenciando este spec al cerrar la
   Fase 1; Fases 2 y 3 quedan explícitamente abiertas y remitidas a BL-35/BL-29.
