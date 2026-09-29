"""Unit tests for bounded transient document vision preparation."""

from __future__ import annotations

import fitz
import pytest

from src.agent.document_vision import (
    DocumentVisionPreparationError,
    has_extractable_text,
    prepare_visual_pages,
)


def _pdf_with_pages(*texts: str) -> bytes:
    document = fitz.open()
    try:
        for text in texts:
            page = document.new_page()
            if text:
                page.insert_text((72, 72), text)
        return document.tobytes()
    finally:
        document.close()


def test_has_extractable_text_detects_pdf_text_layer() -> None:
    assert has_extractable_text(_pdf_with_pages("Texto extraíble")) is True


def test_has_extractable_text_returns_false_for_image_only_pdf() -> None:
    document = fitz.open()
    try:
        page = document.new_page()
        pixmap = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 3, 3), 0)
        page.insert_image(fitz.Rect(72, 72, 75, 75), stream=pixmap.tobytes("png"))
        content = document.tobytes()
    finally:
        document.close()

    assert has_extractable_text(content) is False


def test_has_extractable_text_returns_false_for_blank_pdf_page() -> None:
    assert has_extractable_text(_pdf_with_pages("")) is False


def test_has_extractable_text_detects_text_on_later_page() -> None:
    assert has_extractable_text(_pdf_with_pages("", "Texto posterior")) is True


@pytest.mark.parametrize("content", [b"", b"%PDF-not-a-real-document"])
def test_has_extractable_text_rejects_invalid_pdf(content: bytes) -> None:
    with pytest.raises(DocumentVisionPreparationError, match="^pdf_text_detection_failed$"):
        has_extractable_text(content)


def test_has_extractable_text_rejects_encrypted_pdf() -> None:
    document = fitz.open(stream=_pdf_with_pages("privado"), filetype="pdf")
    try:
        content = document.tobytes(
            encryption=fitz.PDF_ENCRYPT_AES_256,
            owner_pw="owner",
            user_pw="user",
        )
    finally:
        document.close()

    with pytest.raises(DocumentVisionPreparationError, match="^pdf_text_detection_failed$"):
        has_extractable_text(content)


def test_prepare_visual_pages_passes_through_images() -> None:
    pages = prepare_visual_pages(b"\x89PNG\r\n\x1a\nbody", "image/png", max_pdf_pages=3)

    assert len(pages) == 1
    assert pages[0].mime_type == "image/png"


def test_prepare_visual_pages_rejects_invalid_pdf() -> None:
    with pytest.raises(DocumentVisionPreparationError, match="pdf_render_failed"):
        prepare_visual_pages(b"%PDF-not-a-real-document", "application/pdf", max_pdf_pages=3)
