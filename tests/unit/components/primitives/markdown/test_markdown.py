"""Unit tests for :class:`bretzel.components.primitives.markdown.Markdown`."""

from __future__ import annotations

import pytest

from bretzel.components.base import ComponentUsageError
from bretzel.components.base.testing import render_isolated
from bretzel.components.primitives.markdown import MARKDOWN_THEME, Markdown
from bretzel.core.serialize import serialize


def _render(text: str | None = None, **kwargs: object) -> str:
    with render_isolated():
        return serialize(Markdown(text, **kwargs).render())


class TestLiteralRender:
    def test_wrapper_carries_root_class(self) -> None:
        html = _render("hi")
        assert "bz-markdown" in html
        assert "block w-full" in html

    def test_heading_levels_get_distinct_classes(self) -> None:
        html = _render("# h1\n\n## h2\n\n### h3\n\n#### h4\n\n##### h5\n\n###### h6")
        # Each heading carries its level-specific class from the theme.
        for level in range(1, 7):
            expected = MARKDOWN_THEME["slots"][f"h{level}"].split()[0]
            assert f"<h{level}" in html
            assert expected in html

    def test_paragraph_styled(self) -> None:
        html = _render("just a paragraph")
        assert "<p class=" in html
        assert "leading-relaxed" in html
        assert "just a paragraph" in html

    def test_unordered_list(self) -> None:
        html = _render("- one\n- two\n- three")
        assert "<ul class=" in html
        assert "list-disc" in html
        assert html.count("<li") == 3

    def test_ordered_list(self) -> None:
        html = _render("1. one\n2. two")
        assert "<ol class=" in html
        assert "list-decimal" in html

    def test_blockquote(self) -> None:
        html = _render("> quoted")
        assert "<blockquote" in html
        assert "border-l-(length:--bz-stroke-accent)" in html

    def test_thematic_break(self) -> None:
        html = _render("a\n\n---\n\nb")
        assert "<hr" in html
        assert "border-t" in html

    def test_strong_and_emphasis(self) -> None:
        html = _render("**bold** and *italic*")
        assert "<strong" in html
        assert "font-semibold" in html
        assert "<em" in html
        assert ">italic<" in html

    def test_inline_code_styled(self) -> None:
        html = _render("Use `print()` here.")
        assert "<code" in html
        assert "font-mono" in html
        assert "print()" in html

    def test_link_with_classes(self) -> None:
        html = _render("[bretzel](https://bretzel.dev)")
        assert '<a href="https://bretzel.dev"' in html
        assert "text-primary" in html
        assert ">bretzel</a>" in html

    def test_image_with_classes(self) -> None:
        html = _render("![cat](https://example.com/cat.png)")
        assert "<img" in html
        assert 'src="https://example.com/cat.png"' in html
        assert "max-w-full" in html

    def test_long_document_keeps_order(self) -> None:
        text = "# A\n\n## B\n\nbody\n\n## C\n\nmore"
        html = _render(text)
        assert html.find("A") < html.find("B") < html.find("body") < html.find("C")


class TestSecurity:
    def test_script_tag_escaped(self) -> None:
        html = _render("Hello <script>alert(1)</script> world")
        assert "<script>" not in html
        assert "&lt;script&gt;" in html

    def test_embedded_html_does_not_execute(self) -> None:
        html = _render("<img onerror=alert(1) src=x>")
        # The literal ``onerror`` may survive as escaped text but the
        # ``<img>`` tag itself must not — ``escape=True`` forbids raw
        # HTML.
        assert "<img onerror" not in html

    def test_javascript_url_in_link_neutralised(self) -> None:
        html = _render("[click](javascript:alert(1))")
        # mistune's ``safe_url`` rewrites harmful protocols.
        assert 'href="javascript:' not in html
        assert "#harmful-link" in html

    def test_vbscript_url_in_link_neutralised(self) -> None:
        html = _render("[click](vbscript:msgbox)")
        assert 'href="vbscript:' not in html
        assert "#harmful-link" in html

    def test_data_url_image_allowed(self) -> None:
        # Image data URIs are in ``GOOD_DATA_PROTOCOLS`` and survive.
        html = _render("![pic](data:image/png;base64,iVBORw0KGgo=)")
        assert "data:image/png;base64" in html

    def test_non_image_data_url_blocked(self) -> None:
        html = _render("[link](data:text/html,<script>alert(1)</script>)")
        assert "#harmful-link" in html

    def test_inline_code_escapes_html_tags(self) -> None:
        # Regression : mistune passes codespan content RAW (default
        # impl calls escape_text). Without escaping we'd inject a
        # literal ``<script>`` and the browser would suspend the
        # whole render right after the opening backtick.
        html = _render("Use `<script>alert(1)</script>` carefully.")
        assert "<script>" not in html
        assert "&lt;script&gt;" in html
        assert "<code" in html

    def test_inline_code_escapes_ampersand(self) -> None:
        html = _render("`a & b`")
        assert "&amp;" in html


class TestFencedCodeBlocks:
    def test_pygments_classes_on_python_block(self) -> None:
        html = _render("```python\nimport os\n```")
        # Pygments keyword span class for ``import``.
        assert 'class="kn"' in html or 'class="k"' in html
        assert "<pre" in html

    def test_wrapper_inherits_bz_code_theme(self) -> None:
        html = _render("```python\nx = 1\n```")
        assert "bz-code" in html
        assert "font-mono" in html

    def test_unknown_lang_falls_back_no_crash(self) -> None:
        html = _render("```not-a-lang\nblob\n```")
        assert "<pre" in html
        assert "blob" in html

    def test_fence_without_lang_renders_text(self) -> None:
        html = _render("```\nplain text\n```")
        assert "<pre" in html
        assert "plain text" in html

    def test_special_chars_in_fenced_code_escaped(self) -> None:
        html = _render("```python\nx = '<tag>'\n```")
        assert "<tag>" not in html
        assert "&lt;tag&gt;" in html

    def test_consecutive_fences_have_vertical_breathing(self) -> None:
        # Standalone ``ui.code`` carries no ``mb-3`` (its parent layout
        # decides spacing). Inside markdown two fences in a row would
        # touch — block_code adds ``mb-3`` to the wrapper class.
        html = _render(
            "```python\na = 1\n```\n\n"
            "```python\nb = 2\n```"
        )
        # At least one ``<pre>`` carries ``mb-3``.
        assert "mb-3" in html
        # Both fences rendered.
        assert html.count("<pre") == 2


class TestTablePlugin:
    def test_table_emits_table_thead_tbody(self) -> None:
        text = "| a | b |\n|---|---|\n| 1 | 2 |"
        html = _render(text)
        assert "<table" in html
        assert "<thead" in html
        assert "<tbody" in html
        assert "<th" in html
        assert "<td" in html

    def test_table_classes_from_theme(self) -> None:
        text = "| a | b |\n|---|---|\n| 1 | 2 |"
        html = _render(text)
        assert "w-full border-collapse" in html
        assert "font-semibold" in html  # th class
        # ``border-b`` appears in both ``th`` and ``td`` theme entries.
        assert "border-b-(length:--bz-stroke) border-text/20" in html
        assert "border-b-(length:--bz-stroke) border-text/10" in html

    def test_table_alignment_emitted(self) -> None:
        text = "| a | b |\n|:--|--:|\n| 1 | 2 |"
        html = _render(text)
        assert "text-align: left" in html
        assert "text-align: right" in html


class TestStrikethroughPlugin:
    def test_strikethrough_emits_del_with_class(self) -> None:
        html = _render("~~gone~~")
        assert "<del" in html
        assert "line-through" in html


class TestEdgeCases:
    def test_empty_string(self) -> None:
        html = _render("")
        assert "<div" in html
        assert "bz-markdown" in html
        # No children — empty wrapper.
        assert "</div>" in html

    def test_none_text(self) -> None:
        html = _render(None)
        assert "<div" in html
        assert "</div>" in html

    def test_emoji_and_unicode(self) -> None:
        html = _render("Ship 🚀 — שלום — 中文")
        assert "🚀" in html
        assert "שלום" in html
        assert "中文" in html

    def test_classes_kwarg_appends_to_root(self) -> None:
        html = _render("hi", classes="ring-2")
        assert "bz-markdown" in html
        assert "ring-2" in html

    def test_very_long_paragraph(self) -> None:
        long_text = "lorem ipsum " * 200
        html = _render(long_text)
        assert "<p" in html
        assert "lorem ipsum" in html


class TestBindingRejected:
    def test_client_binding_raises(self) -> None:
        # Markdown is server-only. A binding would emit a ``<span
        # bz-text>`` and collapse the whole structure to plain text —
        # silently misleading. The constructor rejects bindings with
        # a clear ComponentUsageError so the failure is loud.
        from bretzel.state import ClientState, field
        from bretzel.state.scopes.client import rendering_scope

        class _MdClient(ClientState, persist="memory"):
            body: str = field(default="# Hi")

        with render_isolated(), rendering_scope():
            state = _MdClient()
            with pytest.raises(ComponentUsageError, match="ClientBinding"):
                Markdown(state.body)

    def test_client_expression_raises(self) -> None:
        from bretzel.state.scopes.client import ClientExpression

        expr = ClientExpression("$bz.state.MyState.default.body")
        with render_isolated():
            with pytest.raises(ComponentUsageError, match="ClientBinding"):
                Markdown(expr)

    def test_bindable_props_empty(self) -> None:
        assert Markdown.BINDABLE_PROPS == ()
