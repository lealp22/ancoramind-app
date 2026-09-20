"""Telegram HTML rendering for the model's Markdown replies (BL-29).

The governed Agent runs with Markdown output enabled, so replies contain
``**bold**``, ``### headings`` and similar markup. Telegram renders formatting
only when the delivery declares a parse mode: until now replies were sent as
plain text and users saw the raw markers.

The reply is model output, that is untrusted DATA (AGENTS.md §2.8), so:

* every literal character is escaped and tags come only from the fixed
  whitelist in this module — the text can never inject markup;
* emphasis is converted only when its closing marker exists in the same chunk,
  so a chunk boundary can drop formatting but never emit a broken tag;
* links are emitted only for ``http(s)`` URLs free of quotes and angle brackets,
  so the ``href`` attribute cannot be broken from the content.

Rendering may therefore lose emphasis, never meaning or deliverability.
"""

from __future__ import annotations

import re

MAX_MESSAGE_CHARS = 4096
"""Telegram ``sendMessage`` hard limit used by the delivery fallback."""

_FENCE_LINE = re.compile(r"^\s*```")
_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
_BULLET = re.compile(r"^([-*+])\s+(.*)$")
_CODE_SPAN = re.compile(r"`([^`\n]+)`")
_LINK = re.compile(r"\[([^\]\n]+)\]\((https?://[^\s)\"<>]+)\)")
_BOLD = re.compile(r"\*\*(?=\S)(.+?)(?<=\S)\*\*", re.DOTALL)
_STRIKE = re.compile(r"~~(?=\S)(.+?)(?<=\S)~~", re.DOTALL)
_ITALIC_STAR = re.compile(r"(?<![\w*])\*(?=\S)([^*\n]+?)(?<=\S)\*(?![\w*])")
_ITALIC_UNDERSCORE = re.compile(r"(?<![\w_])_(?=\S)([^_\n]+?)(?<=\S)_(?![\w_])")


def escape_telegram_html(text: str) -> str:
    """Escape the three characters Telegram's HTML parser interprets."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def markdown_to_telegram_html(text: str) -> str:
    """Render Markdown-ish Agent output as Telegram-compatible HTML.

    Supported: bold, italic, strikethrough, inline code, fenced code blocks,
    headings and bullet lists. Anything else stays as escaped literal text.
    """
    rendered: list[str] = []
    fenced: list[str] | None = None
    for line in text.split("\n"):
        if _FENCE_LINE.match(line):
            if fenced is None:
                fenced = []
            else:
                rendered.append(
                    "<pre>" + escape_telegram_html("\n".join(fenced)) + "</pre>"
                )
                fenced = None
            continue
        if fenced is not None:
            fenced.append(line)
            continue
        rendered.append(_render_line(line))

    if fenced is not None:
        # Unterminated fence (for example a chunk boundary): keep the content as
        # text and never emit a dangling <pre> tag.
        rendered.extend(escape_telegram_html(line) for line in fenced)
    return "\n".join(rendered)


def _render_line(line: str) -> str:
    if not line.strip():
        return ""
    stripped = line.lstrip()
    indent = escape_telegram_html(line[: len(line) - len(stripped)])

    heading = _HEADING.match(stripped)
    if heading:
        return f"{indent}<b>{_render_inline(heading.group(2))}</b>"

    bullet = _BULLET.match(stripped)
    if bullet:
        return f"{indent}• {_render_inline(bullet.group(2))}"

    return indent + _render_inline(stripped)


def _render_inline(text: str) -> str:
    """Render inline emphasis, keeping code spans free of nested markup."""
    parts: list[str] = []
    position = 0
    for match in _CODE_SPAN.finditer(text):
        parts.append(_render_emphasis(text[position : match.start()]))
        parts.append("<code>" + escape_telegram_html(match.group(1)) + "</code>")
        position = match.end()
    parts.append(_render_emphasis(text[position:]))
    return "".join(parts)


def _render_emphasis(segment: str) -> str:
    escaped = escape_telegram_html(segment)
    escaped = _LINK.sub(_link_replacement, escaped)
    return _apply_emphasis(escaped)


def _link_replacement(match: re.Match[str]) -> str:
    """Keep the URL intact: it is already escaped and cannot contain quotes."""
    label = _apply_emphasis(match.group(1))
    return f'<a href="{match.group(2)}">{label}</a>'


def _apply_emphasis(escaped_text: str) -> str:
    """Apply emphasis to already-escaped text using balanced-marker rules."""
    rendered = _BOLD.sub(lambda match: f"<b>{match.group(1)}</b>", escaped_text)
    rendered = _STRIKE.sub(lambda match: f"<s>{match.group(1)}</s>", rendered)
    rendered = _ITALIC_STAR.sub(lambda match: f"<i>{match.group(1)}</i>", rendered)
    return _ITALIC_UNDERSCORE.sub(lambda match: f"<i>{match.group(1)}</i>", rendered)
