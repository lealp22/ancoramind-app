# Tasks — Spec 021: Document Conversion Toolkit

> **Backlog:** BL-38 · abierto 2026-09-29

## Fase 1 — Detección de capa de texto + extracción determinista de PDF (este incremento)

- [x] T1 · `has_extractable_text(content: bytes) -> bool` (PyMuPDF, sin I/O
      externo, sin persistir el PDF) en `src/agent/document_vision.py`.
      Unit tests: PDF con texto, PDF escaneado (sin texto), PDF vacío/corrupto
      (error controlado, no excepción sin capturar). Incremento aislado:
      aún no se invoca desde la tool ni selecciona ruta de extracción.
- [x] T2 · `extract_pdf_text_markdown(content: bytes, *, max_pages: int) ->
      str` usando `pymupdf4llm.to_markdown()`, acotado a `max_pages`.
      **Decisión:** se reutiliza `document_vision_max_pdf_pages` (el mismo
      límite que ya acota la ruta visual) en vez de introducir un tope propio
      — ambas rutas comparten el mismo presupuesto de páginas por documento.
      **Decisión página mixta:** no hay política todo-o-nada; las páginas sin
      texto simplemente no aportan contenido al Markdown resultante
      (`has_extractable_text` ya decidió, con "cualquier página", que esta
      ruta es aplicable). Unit tests: extracción básica, truncado por
      `max_pages`, PDF con páginas mixtas (con/sin texto) —
      `tests/unit/test_document_vision.py`.
- [x] T3 · `pymupdf4llm>=1.24.0,<2.0.0` añadido a `dependencies` en
      `pyproject.toml`. Mismo régimen de licencia que `PyMuPDF` (Artifex
      AGPL/comercial), ya aceptado para esa dependencia.
- [x] T4 · Cableado en `src/agent/tools/documents.py::analyze_document`: para
      `application/pdf` se llama primero a `has_extractable_text`; si es
      `True` se usa `extract_pdf_text_markdown` (sin `visual_pages`); si es
      `False`, o si la extracción determinista falla, se mantiene el camino
      visual (`prepare_visual_pages`).
- [x] T5 · `DocumentService.ingest`/`_extract`/`_build_extraction_prompt`
      aceptan `extracted_text: str | None`, tratado igual que el
      `text_preview` ya existente para `text/*` (mismo acotado
      `MAX_TEXT_PREVIEW_BYTES`, misma serialización JSON escapada — no se creó
      un camino de confianza nuevo; BL-39/specs/022 ya cubre ese escape).
      `tests/unit/test_document_extraction_port.py` prueba el truncado y el
      cierre falso de delimitador se cubre con los tests adversariales ya
      existentes de ese módulo (comparten la misma función de serialización).
- [x] T6 · `tests/unit/test_document_tools.py`:
      `test_analyze_document_uses_deterministic_text_for_pdf_with_text_layer`
      verifica que un PDF con capa de texto llama a `service.ingest` con
      `visual_pages=()` y `extracted_text` no vacío;
      `test_analyze_document_falls_back_to_visual_for_scanned_pdf` verifica lo
      contrario para un PDF sin texto (`visual_pages` con una página,
      `extracted_text=None`).
- [x] T7 (Should Have) · `DocumentService._extract` emite
      `ancora.document.extraction_route` (`deterministic`/`visual`/`none`) vía
      `get_telemetry().counter(...)`, con la clave añadida al allowlist de
      `src/observability/telemetry.py`. Metadata-only (sin contenido ni
      prompts); no se persiste en `ai_extractions` para no acoplar el modelo
      de datos a un detalle de la ruta de infraestructura.
- [x] T8 · `ruff check src/ tests/ scripts/ migrations/`, `mypy src/`,
      `pytest tests/unit/` en verde (693 unit tests). `pytest
      tests/integration/` no se ejecutó — sin PostgreSQL/Docker disponible en
      este incremento y el pipeline de persistencia de documentos no cambió
      de forma (mismo repositorio, misma tabla); pendiente confirmar cuando
      haya infraestructura disponible.
- [x] T9 · `BACKLOG.md` actualizado: Fase 1 de BL-38 marcada implementada
      localmente con referencia a `specs/021`; BL-6 anota que el refinamiento
      "preferir extracción textual" queda resuelto.

## Fase 2 — DOCX determinista (bloqueada por BL-35, no en este incremento)

- [ ] T10 · Tras el cierre de BL-35 (ingesta ofimática con sus límites de
      seguridad), portar `docx_to_md_app.py` (texto + tablas → Markdown, modo
      `remove`/`save` para imágenes) como función determinista análoga a T2,
      detrás del mismo punto de decisión de `analyze_document`.
- [ ] T11 · Reusar los límites de tamaño/profundidad/ZIP ya exigidos por BL-35;
      no introducir un camino de ingesta DOCX paralelo sin esos controles.

## Fase 3 — Export Markdown → PDF (bloqueada por decisión de diseño + BL-29)

- [ ] T12 · Spec-ear (ampliar este documento o crear uno nuevo) el mecanismo de
      generación: DOCX (`markdown_docx_converter.py`, ya portable) + conversor
      DOCX→PDF, vs. HTML→PDF directo. Decidir sin dependencias de sistema
      pesadas (evitar wkhtmltopdf/LibreOffice como requisito de despliegue en
      Railway) y documentar la decisión con límites de tamaño/tiempo.
- [ ] T13 · `propose_export_document`/`execute_export_document` (o justificar
      READ si se decide sin ActionProposal) siguiendo `docs/adding-tools.md`,
      entrega vía `sendDocument` de Telegram.
- [ ] T14 · E2E: exportar una nota o lista TODO real a PDF y recibirla en
      Telegram; evidencia en `verification.md`.
