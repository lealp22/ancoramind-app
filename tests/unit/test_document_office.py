"""Deterministic DOCX/XLSX/PPTX extraction (specs/021 Fase 2 / BL-35) — in-
memory only, same construction style as ``test_document_vision.py`` (no
fixture files)."""

from __future__ import annotations

import io
import re
import zipfile

import docx
import openpyxl
import pytest
from pptx import Presentation

from src.agent.document_office import (
    DocxExtractionError,
    PptxExtractionError,
    XlsxExtractionError,
    extract_docx_text_markdown,
    extract_pptx_text_markdown,
    extract_xlsx_text_markdown,
)

_LIMITS = {"max_blocks": 100, "max_zip_entries": 200, "max_uncompressed_bytes": 50_000_000}
_XLSX_LIMITS = {**_LIMITS, "max_sheets": 20, "max_cols_per_sheet": 50}
_PPTX_LIMITS = {**_LIMITS, "max_slides": 100}


def _docx_bytes(build: object) -> bytes:
    document = docx.Document()
    build(document)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def _extract(content: bytes, **overrides: int) -> str:
    limits = {**_LIMITS, **overrides}
    return extract_docx_text_markdown(content, **limits)


def _xlsx_bytes(build: object) -> bytes:
    workbook = openpyxl.Workbook()
    build(workbook)
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def _extract_xlsx(content: bytes, **overrides: int) -> str:
    limits = {**_XLSX_LIMITS, **overrides}
    return extract_xlsx_text_markdown(content, **limits)


def _pptx_bytes(build: object) -> bytes:
    presentation = Presentation()
    build(presentation)
    buffer = io.BytesIO()
    presentation.save(buffer)
    return buffer.getvalue()


def _extract_pptx(content: bytes, **overrides: int) -> str:
    limits = {**_PPTX_LIMITS, **overrides}
    return extract_pptx_text_markdown(content, **limits)


def test_extracts_heading_paragraph_and_table_as_markdown():
    def build(document: docx.Document) -> None:
        document.add_heading("Informe", level=1)
        document.add_paragraph("Texto normal del párrafo.")
        table = document.add_table(rows=2, cols=2)
        table.cell(0, 0).text = "Nombre"
        table.cell(0, 1).text = "Valor"
        table.cell(1, 0).text = "Velocidad"
        table.cell(1, 1).text = "120"

    markdown = _extract(_docx_bytes(build))

    assert "# Informe" in markdown
    assert "Texto normal del párrafo." in markdown
    assert "| Nombre | Valor |" in markdown
    assert "| Velocidad | 120 |" in markdown


def test_heading_level_maps_to_hash_count():
    def build(document: docx.Document) -> None:
        document.add_heading("Nivel 2", level=2)

    markdown = _extract(_docx_bytes(build))

    assert markdown.strip() == "## Nivel 2"


def test_empty_paragraphs_are_skipped():
    def build(document: docx.Document) -> None:
        document.add_paragraph("")
        document.add_paragraph("Contenido real")
        document.add_paragraph("   ")

    markdown = _extract(_docx_bytes(build))

    assert markdown.strip() == "Contenido real"


def test_truncates_output_at_max_blocks_without_raising():
    def build(document: docx.Document) -> None:
        for i in range(20):
            document.add_paragraph(f"Párrafo {i}")

    markdown = _extract(_docx_bytes(build), max_blocks=5)

    assert "Párrafo 0" in markdown
    assert "Párrafo 4" in markdown
    assert "Párrafo 10" not in markdown
    assert "Párrafo 19" not in markdown


def test_malformed_zip_is_rejected():
    with pytest.raises(DocxExtractionError, match="docx_malformed"):
        _extract(b"this is not a zip file at all")


def test_valid_zip_without_document_xml_is_rejected():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("hello.txt", "not a real docx")
    with pytest.raises(DocxExtractionError, match="docx_malformed"):
        _extract(buffer.getvalue())


def test_too_many_zip_entries_is_rejected():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("word/document.xml", "<root/>")
        for i in range(5):
            archive.writestr(f"junk/{i}.txt", "x")
    with pytest.raises(DocxExtractionError, match="docx_too_many_entries"):
        _extract(buffer.getvalue(), max_zip_entries=3)


def test_zip_bomb_declared_size_is_rejected_without_inflating():
    """A highly compressible entry (small on disk, large once inflated) is
    rejected purely from the central-directory ``file_size`` header — the
    guard checks that declared metadata, it never decompresses the entry."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("word/document.xml", "<root/>")
        archive.writestr("word/bomb.bin", b"\x00" * 2_000_000, zipfile.ZIP_DEFLATED)
    with pytest.raises(DocxExtractionError, match="docx_zip_bomb_suspected"):
        _extract(buffer.getvalue(), max_uncompressed_bytes=1_000_000)


def test_path_traversal_entry_name_is_rejected():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("word/document.xml", "<root/>")
        archive.writestr("../../etc/passwd", "pwned")
    with pytest.raises(DocxExtractionError, match="docx_unsafe_entry_name"):
        _extract(buffer.getvalue())


def test_macro_project_entry_is_rejected():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("word/document.xml", "<root/>")
        archive.writestr("word/vbaProject.bin", b"\x00\x01")
    with pytest.raises(DocxExtractionError, match="docx_macro_rejected"):
        _extract(buffer.getvalue())


def test_xml_entity_declaration_is_rejected_without_a_defusedxml_dependency():
    """OOXML never legitimately declares a DTD/entity; this is the guard
    against XML entity-expansion ("billion laughs") attacks (specs/021)."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(
            "word/document.xml",
            '<!DOCTYPE root [<!ENTITY lol "lol">]><root>&lol;</root>',
        )
    with pytest.raises(DocxExtractionError, match="docx_xml_entity_rejected"):
        _extract(buffer.getvalue())


# ── XLSX ──────────────────────────────────────────────────────────────────


def test_extracts_sheet_as_markdown_table_with_sheet_heading():
    def build(workbook: openpyxl.Workbook) -> None:
        sheet = workbook.active
        sheet.title = "Gastos"
        sheet.append(["Concepto", "Importe"])
        sheet.append(["Taller", 120])

    markdown = _extract_xlsx(_xlsx_bytes(build))

    assert "## Gastos" in markdown
    assert "| Concepto | Importe |" in markdown
    assert "| Taller | 120 |" in markdown


def test_xlsx_formulas_render_the_cached_value_not_the_formula():
    def build(workbook: openpyxl.Workbook) -> None:
        sheet = workbook.active
        sheet.append(["A", "B", "Total"])
        sheet["A2"] = 2
        sheet["B2"] = 3
        sheet["C2"] = "=A2+B2"

    markdown = _extract_xlsx(_xlsx_bytes(build))

    # A freshly-written workbook has no cached formula result (Excel/LibreOffice
    # never computed it), so openpyxl's data_only read returns None for it —
    # the key guarantee is that the literal formula string never appears.
    assert "=A2+B2" not in markdown


def test_xlsx_truncates_rows_across_sheets_by_shared_block_budget():
    def build(workbook: openpyxl.Workbook) -> None:
        sheet = workbook.active
        for i in range(20):
            sheet.append([f"fila {i}"])

    markdown = _extract_xlsx(_xlsx_bytes(build), max_blocks=5)

    assert "fila 0" in markdown
    assert "fila 4" in markdown
    assert "fila 10" not in markdown
    assert "fila 19" not in markdown


def test_xlsx_blank_rows_still_consume_the_shared_budget():
    """An adversarial sheet of blank rows must not iterate unbounded."""

    def build(workbook: openpyxl.Workbook) -> None:
        sheet = workbook.active
        for _ in range(50):
            sheet.append([None, None])
        sheet.append(["nunca llega", "porque el budget ya se agotó"])

    markdown = _extract_xlsx(_xlsx_bytes(build), max_blocks=10)

    assert markdown.strip() == ""


def test_xlsx_respects_max_sheets():
    def build(workbook: openpyxl.Workbook) -> None:
        workbook.active.title = "Uno"
        workbook.active.append(["x"])
        workbook.create_sheet("Dos").append(["y"])
        workbook.create_sheet("Tres").append(["z"])

    markdown = _extract_xlsx(_xlsx_bytes(build), max_sheets=1)

    assert "## Uno" in markdown
    assert "## Dos" not in markdown
    assert "## Tres" not in markdown


def test_xlsx_respects_max_cols_per_sheet():
    def build(workbook: openpyxl.Workbook) -> None:
        workbook.active.append(["a", "b", "c", "d"])

    markdown = _extract_xlsx(_xlsx_bytes(build), max_cols_per_sheet=2)

    assert "| a | b |" in markdown
    assert "c" not in markdown
    assert "d" not in markdown


def test_xlsx_malformed_zip_is_rejected():
    with pytest.raises(XlsxExtractionError, match="xlsx_malformed"):
        _extract_xlsx(b"this is not a zip file at all")


def test_xlsx_zip_bomb_declared_size_is_rejected():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("xl/workbook.xml", "<root/>")
        archive.writestr("xl/bomb.bin", b"\x00" * 2_000_000, zipfile.ZIP_DEFLATED)
    with pytest.raises(XlsxExtractionError, match="xlsx_zip_bomb_suspected"):
        _extract_xlsx(buffer.getvalue(), max_uncompressed_bytes=1_000_000)


def test_xlsx_path_traversal_entry_name_is_rejected():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("xl/workbook.xml", "<root/>")
        archive.writestr("../../etc/passwd", "pwned")
    with pytest.raises(XlsxExtractionError, match="xlsx_unsafe_entry_name"):
        _extract_xlsx(buffer.getvalue())


def test_xlsx_macro_project_entry_is_rejected():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("xl/workbook.xml", "<root/>")
        archive.writestr("xl/vbaProject.bin", b"\x00\x01")
    with pytest.raises(XlsxExtractionError, match="xlsx_macro_rejected"):
        _extract_xlsx(buffer.getvalue())


# ── PPTX ──────────────────────────────────────────────────────────────────


def test_extracts_slide_title_body_and_notes_as_markdown():
    def build(presentation: Presentation) -> None:
        slide = presentation.slides.add_slide(presentation.slide_layouts[1])
        slide.shapes.title.text = "Resumen trimestral"
        slide.placeholders[1].text_frame.text = "Ingresos al alza"
        slide.notes_slide.notes_text_frame.text = "Recordar mencionar Murcia"

    markdown = _extract_pptx(_pptx_bytes(build))

    assert "## Diapositiva 1" in markdown
    assert "Resumen trimestral" in markdown
    assert "Ingresos al alza" in markdown
    assert "> Recordar mencionar Murcia" in markdown


def test_pptx_never_renders_tables_or_images_only_text_and_notes():
    """BL-35 scopes PPTX to text/notes only — tables are deliberately skipped."""

    def build(presentation: Presentation) -> None:
        slide = presentation.slides.add_slide(presentation.slide_layouts[6])
        slide.shapes.add_table(2, 2, 0, 0, 100, 100).table.cell(0, 0).text = "tabla"
        slide.shapes.add_textbox(0, 0, 100, 100).text_frame.text = "texto plano"

    markdown = _extract_pptx(_pptx_bytes(build))

    assert "texto plano" in markdown
    assert "tabla" not in markdown


def test_pptx_truncates_slides_by_shared_block_budget():
    def build(presentation: Presentation) -> None:
        for i in range(5):
            slide = presentation.slides.add_slide(presentation.slide_layouts[6])
            slide.shapes.add_textbox(0, 0, 100, 100).text_frame.text = f"diapositiva {i}"

    markdown = _extract_pptx(_pptx_bytes(build), max_blocks=2)

    assert "diapositiva 0" in markdown
    assert "diapositiva 1" in markdown
    assert "diapositiva 4" not in markdown


def test_pptx_respects_max_slides():
    def build(presentation: Presentation) -> None:
        for i in range(3):
            slide = presentation.slides.add_slide(presentation.slide_layouts[6])
            slide.shapes.add_textbox(0, 0, 100, 100).text_frame.text = f"diapositiva {i}"

    markdown = _extract_pptx(_pptx_bytes(build), max_slides=1)

    assert "diapositiva 0" in markdown
    assert "diapositiva 1" not in markdown


def test_pptx_malformed_zip_is_rejected():
    with pytest.raises(PptxExtractionError, match="pptx_malformed"):
        _extract_pptx(b"this is not a zip file at all")


def test_pptx_zip_bomb_declared_size_is_rejected():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("ppt/presentation.xml", "<root/>")
        archive.writestr("ppt/bomb.bin", b"\x00" * 2_000_000, zipfile.ZIP_DEFLATED)
    with pytest.raises(PptxExtractionError, match="pptx_zip_bomb_suspected"):
        _extract_pptx(buffer.getvalue(), max_uncompressed_bytes=1_000_000)


def test_pptx_path_traversal_entry_name_is_rejected():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("ppt/presentation.xml", "<root/>")
        archive.writestr("../../etc/passwd", "pwned")
    with pytest.raises(PptxExtractionError, match="pptx_unsafe_entry_name"):
        _extract_pptx(buffer.getvalue())


def test_pptx_macro_project_entry_is_rejected():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("ppt/presentation.xml", "<root/>")
        archive.writestr("ppt/vbaProject.bin", b"\x00\x01")
    with pytest.raises(PptxExtractionError, match="pptx_macro_rejected"):
        _extract_pptx(buffer.getvalue())


def test_pptx_too_many_zip_entries_is_rejected():
    def build(presentation: Presentation) -> None:
        presentation.slides.add_slide(presentation.slide_layouts[6])

    with pytest.raises(PptxExtractionError, match="pptx_too_many_entries"):
        _extract_pptx(_pptx_bytes(build), max_zip_entries=10)


# ── Adversarial: "archivo renombrado" — a real Office file of one kind,
# declared/renamed as another (BL-35 pending fixture) ──────────────────────


def _real_docx_bytes() -> bytes:
    def build(document: docx.Document) -> None:
        document.add_paragraph("contenido docx real")

    return _docx_bytes(build)


def _real_xlsx_bytes() -> bytes:
    def build(workbook: openpyxl.Workbook) -> None:
        workbook.active.append(["contenido xlsx real"])

    return _xlsx_bytes(build)


def _real_pptx_bytes() -> bytes:
    def build(presentation: Presentation) -> None:
        slide = presentation.slides.add_slide(presentation.slide_layouts[6])
        slide.shapes.add_textbox(0, 0, 100, 100).text_frame.text = "contenido pptx real"

    return _pptx_bytes(build)


def test_docx_extractor_rejects_a_renamed_xlsx_file():
    with pytest.raises(DocxExtractionError, match="docx_malformed"):
        _extract(_real_xlsx_bytes())


def test_docx_extractor_rejects_a_renamed_pptx_file():
    with pytest.raises(DocxExtractionError, match="docx_malformed"):
        _extract(_real_pptx_bytes())


def test_xlsx_extractor_rejects_a_renamed_docx_file():
    with pytest.raises(XlsxExtractionError, match="xlsx_malformed"):
        _extract_xlsx(_real_docx_bytes())


def test_xlsx_extractor_rejects_a_renamed_pptx_file():
    with pytest.raises(XlsxExtractionError, match="xlsx_malformed"):
        _extract_xlsx(_real_pptx_bytes())


def test_pptx_extractor_rejects_a_renamed_docx_file():
    with pytest.raises(PptxExtractionError, match="pptx_malformed"):
        _extract_pptx(_real_docx_bytes())


def test_pptx_extractor_rejects_a_renamed_xlsx_file():
    with pytest.raises(PptxExtractionError, match="pptx_malformed"):
        _extract_pptx(_real_xlsx_bytes())


# ── Adversarial: "workbook desmesurado" — a sheet that lies about its
# dimensions in the XML, independent of its real row count (BL-35 pending
# fixture; the defense itself — read_only streaming — already existed, this
# proves it against a crafted lie instead of only trusting the comment) ────


def _xlsx_with_lied_dimension(real_rows: int, *, claimed_ref: str) -> bytes:
    """Build a small, real workbook, then rewrite its sheet XML's declared
    ``<dimension>`` to a huge range the real content never actually fills."""

    def build(workbook: openpyxl.Workbook) -> None:
        sheet = workbook.active
        for i in range(real_rows):
            sheet.append([f"fila real {i}"])

    content = _xlsx_bytes(build)
    with zipfile.ZipFile(io.BytesIO(content)) as source:
        entries = {name: source.read(name) for name in source.namelist()}

    sheet_path = next(
        name for name in entries if re.fullmatch(r"xl/worksheets/sheet\d+\.xml", name)
    )
    original = entries[sheet_path]
    assert b"<dimension ref=" in original, "fixture assumption: openpyxl always declares one"
    lied = re.sub(rb'<dimension ref="[^"]*"', f'<dimension ref="{claimed_ref}"'.encode(), original)
    assert lied != original
    entries[sheet_path] = lied

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, data in entries.items():
            archive.writestr(name, data)
    return buffer.getvalue()


def test_xlsx_with_a_lying_oversized_dimension_still_extracts_only_real_rows():
    """A1:XFD1048576 is Excel's absolute maximum sheet size — openpyxl's
    non-streaming reader has historically tried to pre-size for this; the
    ``read_only=True`` streaming read used here must stay bounded by what is
    actually present, never by the declared (and here, false) dimension."""
    content = _xlsx_with_lied_dimension(3, claimed_ref="A1:XFD1048576")

    markdown = _extract_xlsx(content)

    assert "fila real 0" in markdown
    assert "fila real 2" in markdown


def test_xlsx_with_a_lying_dimension_is_still_truncated_by_the_real_shared_budget():
    """The declared dimension must never substitute for the real row-count
    budget enforcement — truncation still happens based on rows actually
    scanned, same as an honest workbook."""
    content = _xlsx_with_lied_dimension(20, claimed_ref="A1:XFD1048576")

    markdown = _extract_xlsx(content, max_blocks=5)

    assert "fila real 0" in markdown
    assert "fila real 4" in markdown
    assert "fila real 10" not in markdown
    assert "fila real 19" not in markdown
