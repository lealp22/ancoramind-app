"""Deterministic DOCX extraction (specs/021 Fase 2 / BL-35) — in-memory only,
same construction style as ``test_document_vision.py`` (no fixture files)."""

from __future__ import annotations

import io
import zipfile

import docx
import pytest

from src.agent.document_office import DocxExtractionError, extract_docx_text_markdown

_LIMITS = {"max_blocks": 100, "max_zip_entries": 200, "max_uncompressed_bytes": 50_000_000}


def _docx_bytes(build: object) -> bytes:
    document = docx.Document()
    build(document)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def _extract(content: bytes, **overrides: int) -> str:
    limits = {**_LIMITS, **overrides}
    return extract_docx_text_markdown(content, **limits)


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
