"""Transient visual preparation for the governed document extraction capability."""

from __future__ import annotations

from src.domain.documents.extraction import DocumentVisualPage


class DocumentVisionPreparationError(RuntimeError):
    """Raised when an allowed document cannot be converted into bounded visual input."""


def prepare_visual_pages(
    content: bytes,
    mime_type: str,
    *,
    max_pdf_pages: int,
) -> tuple[DocumentVisualPage, ...]:
    """Return images for visual extraction without persisting rendered pages.

    JPEG/PNG are passed through directly. PDFs are rendered locally to PNG pages
    using PyMuPDF, capped before calling the vision route to bound cost and input
    volume. The caller owns the original bytes and no rendered page is logged.
    """
    if mime_type in {"image/jpeg", "image/png"}:
        return (DocumentVisualPage(content=content, mime_type=mime_type),)
    if mime_type != "application/pdf":
        return ()

    try:
        import fitz

        document = fitz.open(stream=content, filetype="pdf")
        try:
            pages = tuple(
                DocumentVisualPage(
                    content=page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False).tobytes("png"),
                    mime_type="image/png",
                )
                for page in document[:max_pdf_pages]
            )
        finally:
            document.close()
    except Exception as exc:
        raise DocumentVisionPreparationError("pdf_render_failed") from exc

    if not pages:
        raise DocumentVisionPreparationError("pdf_has_no_pages")
    return pages
