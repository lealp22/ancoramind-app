"""Deterministic Office extraction (specs/021 Fase 2 / BL-35) — DOCX/XLSX/PPTX.

Mirrors ``document_vision.py``'s PDF text route: local, bounded, no network
call, no persisted intermediate. DOCX, XLSX and PPTX are all ZIP containers,
so this module inspects the archive before trusting ``python-docx``/
``openpyxl``/``python-pptx`` to parse it — entry count, unsafe entry names,
total uncompressed size (zip-bomb guard) and a DTD/entity scan (XML entity-
expansion guard, without needing the ``defusedxml`` dependency) are checked
first, rejecting with a safe fixed code, never a raw exception message.
Images, embedded objects, formulas, charts, tables (in PPTX) and hyperlink
targets are never read; only text/computed-value content survives into the
returned Markdown.
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

XLSX_MIME_TYPES = frozenset(
    {"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}
)
"""Deliberately excludes macro-enabled `.xlsm` and the legacy binary `.xls`,
same rationale as ``DOCX_MIME_TYPES``."""

PPTX_MIME_TYPES = frozenset(
    {"application/vnd.openxmlformats-officedocument.presentationml.presentation"}
)
"""Deliberately excludes macro-enabled `.pptm` and the legacy binary `.ppt`,
same rationale as ``DOCX_MIME_TYPES``."""

_DOCX_REQUIRED_ENTRY = "word/document.xml"
_DOCX_FORBIDDEN_ENTRIES = frozenset({"word/vbaProject.bin"})
_XLSX_REQUIRED_ENTRY = "xl/workbook.xml"
_XLSX_FORBIDDEN_ENTRIES = frozenset({"xl/vbaProject.bin"})
_PPTX_REQUIRED_ENTRY = "ppt/presentation.xml"
_PPTX_FORBIDDEN_ENTRIES = frozenset({"ppt/vbaProject.bin"})


class OfficeExtractionError(RuntimeError):
    """Base for Office-document extraction failures (DOCX/XLSX)."""


class DocxExtractionError(OfficeExtractionError):
    """Raised when a declared DOCX cannot be safely inspected or parsed."""


class XlsxExtractionError(OfficeExtractionError):
    """Raised when a declared XLSX cannot be safely inspected or parsed."""


class PptxExtractionError(OfficeExtractionError):
    """Raised when a declared PPTX cannot be safely inspected or parsed."""


def _inspect_office_zip(
    content: bytes,
    *,
    error_cls: type[OfficeExtractionError],
    code_prefix: str,
    required_entry: str,
    forbidden_entries: frozenset[str],
    max_entries: int,
    max_uncompressed_bytes: int,
) -> zipfile.ZipFile:
    """Validate the ZIP container before any entry is parsed by a library.

    Never extracts to disk. Rejects too many entries, unsafe entry names, a
    cumulative uncompressed size over the cap (zip-bomb guard, independent of
    the already-enforced compressed Telegram upload limit), a missing
    required entry, a forbidden macro-project entry (defense in depth in
    case a macro-enabled file arrives with an incorrect declared MIME), and
    any XML entry declaring a DTD/entity (OOXML never legitimately uses one
    — a specific, zero-dependency guard against entity-expansion/"billion
    laughs" attacks on the XML parser both libraries use internally).
    """
    try:
        archive = zipfile.ZipFile(io.BytesIO(content))
    except zipfile.BadZipFile as exc:
        raise error_cls(f"{code_prefix}_malformed") from exc

    infos = archive.infolist()
    if len(infos) > max_entries:
        raise error_cls(f"{code_prefix}_too_many_entries")

    total_uncompressed = 0
    names: set[str] = set()
    for info in infos:
        name = info.filename
        if name.startswith("/") or ".." in PurePosixPath(name).parts:
            raise error_cls(f"{code_prefix}_unsafe_entry_name")
        names.add(name)
        total_uncompressed += info.file_size
        if total_uncompressed > max_uncompressed_bytes:
            raise error_cls(f"{code_prefix}_zip_bomb_suspected")

    if required_entry not in names:
        raise error_cls(f"{code_prefix}_malformed")
    if forbidden_entries & names:
        raise error_cls(f"{code_prefix}_macro_rejected")

    # Total bytes read below are already bounded by the uncompressed-size
    # cap just enforced above.
    for name in names:
        if not name.endswith(".xml"):
            continue
        try:
            data = archive.read(name)
        except Exception as exc:
            raise error_cls(f"{code_prefix}_malformed") from exc
        if b"<!ENTITY" in data or b"<!DOCTYPE" in data:
            raise error_cls(f"{code_prefix}_xml_entity_rejected")
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
    _inspect_office_zip(
        content,
        error_cls=DocxExtractionError,
        code_prefix="docx",
        required_entry=_DOCX_REQUIRED_ENTRY,
        forbidden_entries=_DOCX_FORBIDDEN_ENTRIES,
        max_entries=max_zip_entries,
        max_uncompressed_bytes=max_uncompressed_bytes,
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


def extract_xlsx_text_markdown(
    content: bytes,
    *,
    max_blocks: int,
    max_sheets: int,
    max_cols_per_sheet: int,
    max_zip_entries: int,
    max_uncompressed_bytes: int,
) -> str:
    """Deterministically extract XLSX sheet values as Markdown tables.

    Reads cached computed cell values only (``data_only=True``) — formulas
    are never rendered, only their last-calculated result. ``read_only=True``
    streams rows instead of loading a sheet in full, bounding memory even for
    a workbook that lies about its declared dimensions. ``max_blocks`` bounds
    total rows scanned across all sheets combined — including blank rows,
    same shared-budget philosophy as DOCX counting every paragraph — so an
    adversarial sheet full of blank rows cannot cause unbounded iteration.
    ``max_sheets``/``max_cols_per_sheet`` bound breadth. No images, charts,
    comments or external links are ever read.
    """
    _inspect_office_zip(
        content,
        error_cls=XlsxExtractionError,
        code_prefix="xlsx",
        required_entry=_XLSX_REQUIRED_ENTRY,
        forbidden_entries=_XLSX_FORBIDDEN_ENTRIES,
        max_entries=max_zip_entries,
        max_uncompressed_bytes=max_uncompressed_bytes,
    )
    try:
        import openpyxl

        workbook = openpyxl.load_workbook(io.BytesIO(content), data_only=True, read_only=True)
    except XlsxExtractionError:
        raise
    except Exception as exc:
        raise XlsxExtractionError("xlsx_malformed") from exc

    lines: list[str] = []
    remaining = max_blocks
    try:
        for sheet_name in workbook.sheetnames[:max_sheets]:
            if remaining <= 0:
                break
            sheet_lines, consumed = _render_sheet_markdown(
                workbook[sheet_name], max_rows=remaining, max_cols=max_cols_per_sheet
            )
            if sheet_lines:
                lines.append(f"## {sheet_name}")
                lines.extend(sheet_lines)
            remaining -= consumed
    except XlsxExtractionError:
        raise
    except Exception as exc:
        raise XlsxExtractionError("xlsx_malformed") from exc
    finally:
        workbook.close()

    return "\n\n".join(lines)


def extract_pptx_text_markdown(
    content: bytes,
    *,
    max_blocks: int,
    max_slides: int,
    max_zip_entries: int,
    max_uncompressed_bytes: int,
) -> str:
    """Deterministically extract PPTX slide text and speaker notes as Markdown.

    Only shapes with a text frame are read (titles, body placeholders, text
    boxes) plus each slide's speaker notes — never tables, charts, images or
    embedded objects (BL-35 scopes PPTX to "texto/notas" only). ``max_slides``
    bounds breadth; ``max_blocks`` bounds total text blocks (one per shape or
    notes frame, blank or not) scanned across all slides combined, same
    shared-budget philosophy as DOCX/XLSX — an adversarial slide packed with
    non-text shapes cannot cause unbounded iteration.
    """
    _inspect_office_zip(
        content,
        error_cls=PptxExtractionError,
        code_prefix="pptx",
        required_entry=_PPTX_REQUIRED_ENTRY,
        forbidden_entries=_PPTX_FORBIDDEN_ENTRIES,
        max_entries=max_zip_entries,
        max_uncompressed_bytes=max_uncompressed_bytes,
    )
    try:
        from pptx import Presentation

        presentation = Presentation(io.BytesIO(content))
    except PptxExtractionError:
        raise
    except Exception as exc:
        raise PptxExtractionError("pptx_malformed") from exc

    lines: list[str] = []
    remaining = max_blocks
    try:
        for index, slide in enumerate(presentation.slides, start=1):
            if index > max_slides or remaining <= 0:
                break
            slide_lines, consumed = _render_slide_markdown(slide, max_blocks=remaining)
            if slide_lines:
                lines.append(f"## Diapositiva {index}")
                lines.extend(slide_lines)
            remaining -= consumed
    except Exception as exc:
        raise PptxExtractionError("pptx_malformed") from exc

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


def _render_sheet_markdown(sheet: Any, *, max_rows: int, max_cols: int) -> tuple[list[str], int]:
    """Render one XLSX worksheet (streamed, ``values_only``) as a pipe table.

    Every scanned row counts toward ``consumed``, blank or not — this is
    what keeps an adversarial sheet of blank rows from iterating unbounded.
    """
    lines: list[str] = []
    consumed = 0
    header: list[str] | None = None
    for row in sheet.iter_rows(values_only=True):
        if consumed >= max_rows:
            break
        consumed += 1
        values = [
            "" if cell is None else str(cell).strip().replace("\n", " ") for cell in row[:max_cols]
        ]
        if not any(values):
            continue
        if header is None:
            header = values
            lines.append("| " + " | ".join(header) + " |")
            lines.append("| " + " | ".join("---" for _ in header) + " |")
        else:
            lines.append("| " + " | ".join(values) + " |")
    return lines, consumed


def _render_slide_markdown(slide: Any, *, max_blocks: int) -> tuple[list[str], int]:
    """Render one PPTX slide's text shapes + speaker notes as plain lines.

    Every scanned shape counts toward ``consumed``, text frame or not — this
    is what keeps a slide packed with non-text shapes from iterating
    unbounded (same philosophy as DOCX paragraphs / XLSX rows).
    """
    lines: list[str] = []
    consumed = 0
    for shape in slide.shapes:
        if consumed >= max_blocks:
            return lines, consumed
        consumed += 1
        if not getattr(shape, "has_text_frame", False):
            continue
        text = shape.text_frame.text.strip()
        if text:
            lines.append(text)
    if consumed < max_blocks and getattr(slide, "has_notes_slide", False):
        consumed += 1
        notes_text = slide.notes_slide.notes_text_frame.text.strip()
        if notes_text:
            lines.append(f"> {notes_text}")
    return lines, consumed


__all__ = [
    "DOCX_MIME_TYPES",
    "PPTX_MIME_TYPES",
    "XLSX_MIME_TYPES",
    "DocxExtractionError",
    "OfficeExtractionError",
    "PptxExtractionError",
    "XlsxExtractionError",
    "extract_docx_text_markdown",
    "extract_pptx_text_markdown",
    "extract_xlsx_text_markdown",
]
