"""Deterministic DOCX extraction (specs/021 Fase 2 / BL-35) — DOCX only.

Mirrors ``document_vision.py``'s PDF text route: local, bounded, no network
call, no persisted intermediate. A DOCX is a ZIP container, so this module
inspects the archive before trusting ``python-docx`` to parse it — entry
count, unsafe entry names and total uncompressed size (zip-bomb guard) are
checked first and reject with a safe fixed code, never a raw exception
message. Images, embedded objects and hyperlink targets are never read;
only text content survives into the returned Markdown.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import PurePosixPath
from typing import Any

DOCX_MIME_TYPES = frozenset(
    {"application/vnd.openxmlformats-officedocument.wordprocessingml.document"}
)
"""Deliberately excludes macro-enabled `.docm` and the legacy binary `.doc` —
those MIME types fall through to the existing generic (visual) path
unchanged, which already fails closed to no extraction for them."""

_REQUIRED_ENTRY = "word/document.xml"
_MACRO_ENTRY = "word/vbaProject.bin"


class DocxExtractionError(RuntimeError):
    """Raised when a declared DOCX cannot be safely inspected or parsed."""


def _inspect_docx_zip(
    content: bytes,
    *,
    max_entries: int,
    max_uncompressed_bytes: int,
) -> zipfile.ZipFile:
    """Validate the ZIP container before any entry is read by ``python-docx``.

    Never extracts to disk. Rejects too many entries, unsafe entry names,
    a cumulative uncompressed size over the cap (zip-bomb guard, independent
    of the already-enforced compressed Telegram upload limit), a missing
    ``word/document.xml``, or a present ``vbaProject.bin`` (defense in depth
    in case a macro-enabled file arrives with an incorrect declared MIME).
    """
    try:
        archive = zipfile.ZipFile(io.BytesIO(content))
    except zipfile.BadZipFile as exc:
        raise DocxExtractionError("docx_malformed") from exc

    infos = archive.infolist()
    if len(infos) > max_entries:
        raise DocxExtractionError("docx_too_many_entries")

    total_uncompressed = 0
    names: set[str] = set()
    for info in infos:
        name = info.filename
        if name.startswith("/") or ".." in PurePosixPath(name).parts:
            raise DocxExtractionError("docx_unsafe_entry_name")
        names.add(name)
        total_uncompressed += info.file_size
        if total_uncompressed > max_uncompressed_bytes:
            raise DocxExtractionError("docx_zip_bomb_suspected")

    if _REQUIRED_ENTRY not in names:
        raise DocxExtractionError("docx_malformed")
    if _MACRO_ENTRY in names:
        raise DocxExtractionError("docx_macro_rejected")
    return archive


def extract_docx_text_markdown(
    content: bytes,
    *,
    max_blocks: int,
    max_zip_entries: int,
    max_uncompressed_bytes: int,
) -> str:
    """Deterministically extract a DOCX's text/tables as Markdown.

    Paragraphs and tables are rendered in document order (the standard
    python-docx recipe for interleaving ``w:p``/``w:tbl`` body children,
    since ``Document.paragraphs``/``.tables`` are separate flat lists that
    lose that order). ``Heading N`` styles become ``#``-prefixed headings;
    tables become pipe tables. Images, embedded objects, footnotes and
    hyperlink targets are never read. ``max_blocks`` bounds total paragraphs
    plus table rows processed — once exhausted, extraction stops and returns
    what was gathered so far (truncated, never an exception for size alone).
    """
    _inspect_docx_zip(
        content, max_entries=max_zip_entries, max_uncompressed_bytes=max_uncompressed_bytes
    )
    try:
        import docx
        from docx.oxml.table import CT_Tbl
        from docx.oxml.text.paragraph import CT_P
        from docx.table import Table
        from docx.text.paragraph import Paragraph

        document = docx.Document(io.BytesIO(content))
    except DocxExtractionError:
        raise
    except Exception as exc:
        raise DocxExtractionError("docx_malformed") from exc

    lines: list[str] = []
    remaining = max_blocks
    try:
        for child in document.element.body.iterchildren():
            if remaining <= 0:
                break
            if isinstance(child, CT_P):
                paragraph = Paragraph(child, document)
                text = paragraph.text.strip()
                remaining -= 1
                if not text:
                    continue
                level = _heading_level(paragraph)
                lines.append(f"{'#' * level} {text}" if level else text)
            elif isinstance(child, CT_Tbl):
                table_lines, consumed = _render_table_markdown(
                    Table(child, document), max_rows=remaining
                )
                lines.extend(table_lines)
                remaining -= consumed
    except Exception as exc:
        raise DocxExtractionError("docx_malformed") from exc

    return "\n\n".join(lines)


def _heading_level(paragraph: Any) -> int:
    """Return 1-6 for a ``Heading N`` style, 0 for anything else."""
    style = getattr(paragraph, "style", None)
    name = getattr(style, "name", None) if style is not None else None
    if not isinstance(name, str) or not name.startswith("Heading "):
        return 0
    suffix = name.removeprefix("Heading ").strip()
    if suffix.isdigit() and 1 <= int(suffix) <= 6:
        return int(suffix)
    return 0


def _render_table_markdown(table: Any, *, max_rows: int) -> tuple[list[str], int]:
    """Render a ``python-docx`` ``Table`` as a Markdown pipe table.

    Returns the rendered lines and the number of rows actually consumed
    from ``max_rows``, so the caller can keep a single shared block budget.
    """
    rows = list(table.rows)
    bounded_rows = rows[:max_rows]
    if not bounded_rows:
        return [], 0
    lines: list[str] = []
    header = [cell.text.strip().replace("\n", " ") for cell in bounded_rows[0].cells]
    lines.append("| " + " | ".join(header) + " |")
    lines.append("| " + " | ".join("---" for _ in header) + " |")
    for row in bounded_rows[1:]:
        values = [cell.text.strip().replace("\n", " ") for cell in row.cells]
        lines.append("| " + " | ".join(values) + " |")
    return lines, len(bounded_rows)


__all__ = ["DOCX_MIME_TYPES", "DocxExtractionError", "extract_docx_text_markdown"]
