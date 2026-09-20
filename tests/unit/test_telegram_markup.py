"""Unit tests for Telegram HTML rendering of model Markdown (BL-29)."""

from __future__ import annotations

import re

import pytest

from src.notifications.markup import (
    escape_telegram_html,
    markdown_to_telegram_html,
)

_TAG_PATTERN = re.compile(r'</?(?:b|i|s|u|code|pre|a(?: href="[^"]*")?)>')


class TestEscaping:
    def test_escapes_the_three_interpreted_characters(self) -> None:
        assert escape_telegram_html("a & b < c > d") == "a &amp; b &lt; c &gt; d"

    def test_untrusted_markup_never_reaches_telegram(self) -> None:
        rendered = markdown_to_telegram_html("<script>alert('x')</script>")

        assert "&lt;script&gt;" in rendered
        assert "<script>" not in rendered


class TestInlineRendering:
    def test_bold_is_rendered(self) -> None:
        assert markdown_to_telegram_html("**hola**") == "<b>hola</b>"

    @pytest.mark.parametrize(
        "text,expected",
        [
            ("*hola*", "<i>hola</i>"),
            ("_hola_", "<i>hola</i>"),
            ("~~hola~~", "<s>hola</s>"),
        ],
    )
    def test_emphasis_variants(self, text: str, expected: str) -> None:
        assert markdown_to_telegram_html(text) == expected

    def test_underscores_inside_words_are_literal(self) -> None:
        assert markdown_to_telegram_html("documento_final y otro_nombre") == (
            "documento_final y otro_nombre"
        )

    def test_unbalanced_marker_stays_literal(self) -> None:
        assert markdown_to_telegram_html("**abierto sin cerrar") == "**abierto sin cerrar"

    def test_heading_renders_as_bold_without_markers(self) -> None:
        assert markdown_to_telegram_html("### Resumen") == "<b>Resumen</b>"

    def test_bullets_become_a_middle_dot(self) -> None:
        assert markdown_to_telegram_html("- uno\n* dos") == "• uno\n• dos"

    def test_nested_emphasis_is_balanced(self) -> None:
        rendered = markdown_to_telegram_html("*a **b** c*")

        assert rendered == "<i>a <b>b</b> c</i>"


class TestCodeRendering:
    def test_inline_code_is_escaped_and_not_emphasized(self) -> None:
        assert markdown_to_telegram_html("usa `a < b` y `**x**`") == (
            "usa <code>a &lt; b</code> y <code>**x**</code>"
        )

    def test_fenced_block_becomes_pre(self) -> None:
        rendered = markdown_to_telegram_html("```\n**no**\n<tag>\n```")

        assert rendered == "<pre>**no**\n&lt;tag&gt;</pre>"

    def test_unterminated_fence_never_leaves_a_dangling_pre(self) -> None:
        rendered = markdown_to_telegram_html("```\ncodigo cortado")

        assert "<pre>" not in rendered
        assert rendered.endswith("codigo cortado")


class TestLinks:
    def test_http_link_is_rendered_with_escaped_url(self) -> None:
        rendered = markdown_to_telegram_html("[web](https://e.com/a?b=1&c=2)")

        assert rendered == '<a href="https://e.com/a?b=1&amp;c=2">web</a>'

    def test_link_with_quotes_in_url_stays_literal_text(self) -> None:
        rendered = markdown_to_telegram_html('[x](https://e.com/a"onmouseover=alert(1))')

        assert "<a" not in rendered
        assert "onmouseover" in rendered

    @pytest.mark.parametrize(
        "url",
        ["javascript:alert(1)", "ftp://e.com/x", "data:text/html;base64,AAA"],
    )
    def test_non_http_schemes_are_not_linked(self, url: str) -> None:
        rendered = markdown_to_telegram_html(f"[x]({url})")

        assert "<a" not in rendered


def test_every_angle_bracket_belongs_to_a_whitelisted_tag() -> None:
    hostile = (
        "<b> **a** <i> & [x](https://e.com/\"onmouseover=alert(1)) ` <script> "
        "**b** <a href='#'> <pre> ``` ~~c~~ "
    )

    rendered = markdown_to_telegram_html(hostile)
    without_tags = _TAG_PATTERN.sub("", rendered)

    assert "<" not in without_tags
    assert ">" not in without_tags


def test_plain_conversation_is_left_understandable() -> None:
    text = "Hola:\n\n- te dejo **notas** y el enlace [ficha](https://e.com/f)\n\n¿Seguimos?"

    assert markdown_to_telegram_html(text) == (
        "Hola:\n\n• te dejo <b>notas</b> y el enlace "
        '<a href="https://e.com/f">ficha</a>\n\n¿Seguimos?'
    )
