"""Unit tests for bounded transient document vision preparation."""

from __future__ import annotations

import pytest

from src.agent.document_vision import DocumentVisionPreparationError, prepare_visual_pages


def test_prepare_visual_pages_passes_through_images() -> None:
    pages = prepare_visual_pages(b"\x89PNG\r\n\x1a\nbody", "image/png", max_pdf_pages=3)

    assert len(pages) == 1
    assert pages[0].mime_type == "image/png"


def test_prepare_visual_pages_rejects_invalid_pdf() -> None:
    with pytest.raises(DocumentVisionPreparationError, match="pdf_render_failed"):
        prepare_visual_pages(b"%PDF-not-a-real-document", "application/pdf", max_pdf_pages=3)
