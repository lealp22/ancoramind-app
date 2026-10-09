"""Deterministic Markdown → PDF export (BL-38 Fase 3).

No new PDF dependency: PyMuPDF (already approved and used throughout the
document pipeline) renders real HTML — headings, lists, tables — to PDF via
its ``Story``/``DocumentWriter`` API. Only ``markdown`` (BSD-3-Clause, pure
Python) is new, for the Markdown→HTML step. Nothing here is persisted to
disk or ``DocumentStorage``: the input is model-synthesized content, not a
user-uploaded document, so it is rendered in memory and handed to the
caller for immediate delivery.
"""

from __future__ import annotations

import io


class DocumentExportError(RuntimeError):
    """Raised when Markdown cannot be safely or successfully rendered to PDF."""


def render_markdown_to_pdf(
    markdown_text: str,
    *,
    title: str | None,
    max_markdown_chars: int,
    max_pages: int,
    max_pdf_bytes: int,
) -> bytes:
    """Render Markdown to a bounded PDF, truncated rather than rejected by size.

    Rejects empty or over-length input before touching any library. Stops
    rendering once ``max_pages`` is reached — a pathological input yields a
    truncated PDF, never an unbounded one. The caller must check the result
    against ``max_pdf_bytes`` only to decide whether a render this large is
    still safe to upload; the cap is enforced here directly.
    """
    text = markdown_text.strip()
    if not text:
        raise DocumentExportError("export_empty_output")
    if len(text) > max_markdown_chars:
        raise DocumentExportError("export_markdown_too_long")

    try:
        import fitz
        import markdown

        body_html = markdown.markdown(text, extensions=["tables", "fenced_code"])
        heading = f"<h1>{_escape_html(title)}</h1>" if title and title.strip() else ""
        html = f"{heading}{body_html}"

        story = fitz.Story(html=html)
        mediabox = fitz.paper_rect("a4")
        where = mediabox + (36, 36, -36, -36)
        buffer = io.BytesIO()
        writer = fitz.DocumentWriter(buffer)
        try:
            pages = 0
            more = 1
            while more and pages < max_pages:
                device = writer.begin_page(mediabox)
                more, _ = story.place(where)
                story.draw(device)
                writer.end_page()
                pages += 1
        finally:
            writer.close()
    except DocumentExportError:
        raise
    except Exception as exc:
        raise DocumentExportError("export_render_failed") from exc

    content = buffer.getvalue()
    if not content:
        raise DocumentExportError("export_empty_output")
    if len(content) > max_pdf_bytes:
        raise DocumentExportError("export_render_failed")
    return content


def _escape_html(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


__all__ = ["DocumentExportError", "render_markdown_to_pdf"]
