"""Transient visual preparation for the governed document extraction capability."""

from __future__ import annotations

from src.domain.documents.extraction import DocumentVisualPage


class DocumentVisionPreparationError(RuntimeError):
    """Raised when an allowed document cannot be converted into bounded visual input."""


def has_extractable_text(content: bytes) -> bool:
    """Detect a PDF text layer locally, without storing or sending the document.

    This only classifies bytes; it does not select an extraction route or grant
    permission to ingest a document. Invalid, empty and encrypted PDFs fail
    closed with an error that does not expose document content.
    """
    try:
        import fitz

        document = fitz.open(stream=content, filetype="pdf")
        try:
            if document.needs_pass:
                raise DocumentVisionPreparationError("pdf_text_detection_failed")
            if document.page_count == 0:
                raise DocumentVisionPreparationError("pdf_has_no_pages")
            return any(page.get_text("text").strip() for page in document)
        finally:
            document.close()
    except DocumentVisionPreparationError:
        raise
    except Exception as exc:
        raise DocumentVisionPreparationError("pdf_text_detection_failed") from exc


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
