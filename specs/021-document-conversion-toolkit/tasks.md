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

## Fase 2 — DOCX determinista ✅ implementado localmente — 2026-10-09 (BL-35)

- [x] T10 · En vez de portar `docx_to_md_app.py` (mammoth + markdownify, dos
      dependencias nuevas y soporte Markdown de mammoth marcado
      experimental/deprecado en su propia documentación), se implementó un
      renderer propio sobre `python-docx` (MIT, puro Python):
      `src/agent/document_office.py::extract_docx_text_markdown`, análoga a
      `extract_pdf_text_markdown` (T2) y enganchada en el mismo punto de
      decisión de `analyze_document` (`src/agent/tools/documents.py`).
      Recorre `document.element.body` en orden real (párrafos + tablas
      intercaladas), mapea `Heading N` → `#`×N, tablas → Markdown de pipes;
      nunca lee imágenes, objetos embebidos ni sigue hyperlinks.
- [x] T11 · Límites de seguridad propios (no un camino paralelo sin
      controles): `_inspect_docx_zip` valida nº de entradas ZIP, nombres sin
      `../`/ruta absoluta, suma de tamaños sin comprimir contra un tope
      (zip-bomb por metadato declarado, sin inflar la entrada), exige
      `word/document.xml` y rechaza `word/vbaProject.bin`. `.docm`/`.doc`
      legado quedan excluidos por no estar en el MIME allowlist (caen al
      camino visual existente, sin regresión). Config nueva en
      `src/config.py`: `document_office_max_zip_entries`,
      `document_office_max_uncompressed_bytes`, `document_office_max_blocks`.
      **Alcance real: solo DOCX** — XLSX/PPTX (resto de BL-35) quedan como
      siguiente incremento, no cubiertos aquí. 12 tests nuevos
      (`test_document_office.py` + 2 en `test_document_tools.py`), 982 unit
      tests (suite completa), Ruff y `mypy src/` limpios.

## Fase 3 — Export Markdown → PDF ✅ implementado localmente — 2026-10-09

- [x] T12 · Decidido **sin DOCX como intermedio y sin librería de PDF
      nueva**: PyMuPDF (ya aprobado, usado en toda la Fase 1/BL-6) renderiza
      HTML real — headings, listas, tablas — a PDF vía su API
      `Story`/`DocumentWriter`, confirmado empíricamente (no solo por
      documentación) antes de implementar. Solo se añade `markdown`
      (BSD-3-Clause, puro Python) para el paso Markdown→HTML. Cero
      dependencias de sistema (nunca wkhtmltopdf/LibreOffice). Límites en
      `src/config.py`: `document_export_max_markdown_chars` (20000),
      `document_export_max_pages` (20), `document_export_max_pdf_bytes`
      (5MB) — igual que el resto de `document_office_*`, trunca en vez de
      lanzar excepción por tamaño salvo que el resultado final siga
      excediendo el tope.
- [x] T13 · **Decidido automático, un único tool `export_document`, sin
      `propose_*`/`execute_*`** — misma excepción ya aprobada para
      `analyze_document` (AGENTS.md §2.4): no hay mutación canónica y el
      fichero solo llega al propio usuario que lo pidió. Alcance
      deliberadamente genérico: el tool recibe Markdown ya compuesto por el
      modelo (a partir de notas/listas que el modelo ya leyó con sus tools
      de lectura), no hay lógica de exportación específica por dominio.
      Entrega vía `TelegramNotifier.send_document()` (nuevo método, multipart
      a `sendDocument`, misma clasificación de fallos — transporte
      ambiguo, 4xx/5xx definitivo — que `_send_message`). **Riesgo de
      gobernanza documentado, no resuelto:** el envío ocurre a mitad del
      run, fuera del outbox gobernado de specs/013; un fallo justo después
      de un envío correcto podría, en un reintento, duplicar el PDF — nunca
      duplicar una mutación, solo un fichero. Aceptado explícitamente como
      limitación de este incremento, mismo criterio "best-effort, nunca
      bloquea la respuesta principal" ya usado para la captura de
      transcripts de Dream (BL-13). Integrarlo en el outbox real (BL-32)
      queda como seguimiento, no en este incremento.
- [ ] T14 · E2E real con Telegram pendiente (bloqueado por BL-18 — mismo
      criterio que el resto del pipeline documental). 20 tests nuevos
      (7 `test_document_export.py` + 5 `test_telegram_notifier.py` + 7
      `test_export_tools.py` + 1 regresión en `test_instructions.py`,
      1066 unit tests en total), Ruff y `mypy src/` limpios.
