# Tasks — Spec 021: Document Conversion Toolkit

> **Backlog:** BL-38 · abierto 2026-09-29

## Fase 1 — Detección de capa de texto + extracción determinista de PDF (este incremento)

- [ ] T1 · `has_extractable_text(content: bytes) -> bool` (PyMuPDF, sin I/O
      externo, sin persistir el PDF) en `src/agent/document_vision.py`.
      Unit tests: PDF con texto, PDF escaneado (sin texto), PDF vacío/corrupto
      (error controlado, no excepción sin capturar).
- [ ] T2 · `extract_pdf_text_markdown(content: bytes, *, max_pages: int) ->
      str` usando `pymupdf4llm.to_markdown()`, acotado a `max_pages` (alinear
      valor con `document_vision_max_pdf_pages` o un límite propio si se
      decide distinto — documentar la decisión aquí). Unit tests: extracción
      básica, truncado por `max_pages`, PDF con páginas mixtas (con/sin texto)
      — decidir y documentar política todo-o-nada vs. mixta.
- [ ] T3 · Añadir `pymupdf4llm` a `pyproject.toml` (`dependencies`), confirmar
      licencia (MuPDF/AGPL vs. comercial — mismo régimen que `PyMuPDF` ya
      aceptado) y fijar rango de versión compatible con `PyMuPDF>=1.24.0,<2.0.0`.
- [ ] T4 · Cablear la decisión en `src/agent/tools/documents.py::analyze_document`:
      para `application/pdf`, llamar primero a `has_extractable_text`; si es
      `True`, usar `extract_pdf_text_markdown` y pasar el resultado como
      contexto textual a `DocumentService.ingest` (sin `visual_pages`); si es
      `False`, mantener el camino actual (`prepare_visual_pages`).
- [ ] T5 · Ajustar `DocumentService._build_extraction_prompt` (o el punto
      equivalente) para aceptar el texto ya extraído de un PDF con capa de
      texto de la misma forma que ya acepta `text/*` — respetando
      `MAX_TEXT_PREVIEW_BYTES`. Antes de activar la ruta, coordinar con
      BL-39 la serialización de filename y texto no confiables: no aceptar
      `<document_data>` como límite de seguridad; probar cierre de delimitador
      dentro de contenido adversarial y metadatos.
- [ ] T6 · Unit tests de `analyze_document`/`DocumentService.ingest` con un
      PDF-con-texto simulado: verificar que el extraction port de visión NO se
      invoca (mock/spy) y que la extracción persistida referencia la ruta
      determinista (ver T7).
- [ ] T7 (Should Have) · Señal metadata-only de ruta usada (`deterministic` vs.
      `visual`) en la extracción persistida o en telemetría existente, sin
      contenido ni prompts.
- [ ] T8 · `ruff check src/ tests/ scripts/ migrations/`, `mypy src/`,
      `pytest tests/unit/` en verde. Ejecutar `pytest tests/integration/` si
      hay cambios en el pipeline de persistencia.
- [ ] T9 · Actualizar `BACKLOG.md`: cerrar la Fase 1 de BL-38, referenciar
      `specs/021`, y anotar en BL-6 que el refinamiento de "preferir extracción
      textual" queda resuelto.

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
