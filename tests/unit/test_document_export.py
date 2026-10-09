"""Deterministic Markdown→PDF export (BL-38 Fase 3) — in-memory only, no
PostgreSQL, no Telegram. Verifies rendered content by reading the PDF back
with PyMuPDF, same spirit as test_document_vision.py."""

from __future__ import annotations

import fitz
import pytest

from src.agent.document_export import DocumentExportError, render_markdown_to_pdf

_LIMITS = {"max_markdown_chars": 20_000, "max_pages": 20, "max_pdf_bytes": 5_000_000}


def _render(markdown_text: str, **overrides: object) -> bytes:
    title = overrides.pop("title", None)
    limits = {**_LIMITS, **overrides}
    return render_markdown_to_pdf(markdown_text, title=title, **limits)


def _text_of(pdf_bytes: bytes) -> str:
    document = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        return "".join(page.get_text("text") for page in document)
    finally:
        document.close()


def test_renders_headings_lists_and_tables():
    markdown_text = (
        "# Informe\n\nTexto normal.\n\n- Uno\n- Dos\n\n"
        "| Nombre | Valor |\n|---|---|\n| Velocidad | 120 |\n"
    )

    pdf = _render(markdown_text)
    text = _text_of(pdf)

    assert "Informe" in text
    assert "Texto normal." in text
    assert "Uno" in text
    assert "Dos" in text
    assert "Nombre" in text
    assert "Velocidad" in text
    assert "120" in text


def test_optional_title_is_rendered_as_its_own_heading():
    pdf = _render("Contenido breve.", title="Mi exportación")

    text = _text_of(pdf)

    assert "Mi exportación" in text
    assert "Contenido breve." in text


def test_title_with_html_metacharacters_does_not_break_the_page_structure():
    """An unescaped title could prematurely close the `<h1>` wrapper and
    corrupt the rest of the page; escaping keeps the body intact after it."""
    pdf = _render("cuerpo real", title="</h1><h1>inyectado")

    text = _text_of(pdf)

    assert "cuerpo real" in text


def test_empty_markdown_is_rejected():
    with pytest.raises(DocumentExportError, match="export_empty_output"):
        _render("   ")


def test_markdown_over_the_char_limit_is_rejected():
    with pytest.raises(DocumentExportError, match="export_markdown_too_long"):
        _render("x" * 100, max_markdown_chars=50)


def _long_markdown() -> str:
    return "\n\n".join(f"## Sección {i}\n\n" + "párrafo. " * 400 for i in range(30))


def test_truncates_at_max_pages_without_raising():
    pdf = _render(_long_markdown(), max_pages=2, max_markdown_chars=200_000)

    document = fitz.open(stream=pdf, filetype="pdf")
    try:
        assert document.page_count <= 2
    finally:
        document.close()


def test_oversized_rendered_output_is_rejected():
    with pytest.raises(DocumentExportError, match="export_render_failed"):
        _render(_long_markdown(), max_pages=20, max_pdf_bytes=1000, max_markdown_chars=200_000)
