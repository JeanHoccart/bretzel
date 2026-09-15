"""Unit tests for :class:`bretzel.components.primitives.code.Code`."""

from __future__ import annotations

from bretzel.components.base.testing import render_isolated
from bretzel.components.primitives.code import Code
from bretzel.core.serialize import serialize


class TestLiteralRender:
    def test_pre_code_wrapper(self) -> None:
        with render_isolated():
            html = serialize(Code("print('hi')").render())
        assert html.startswith("<pre")
        assert "<code" in html
        assert "</pre>" in html

    def test_wrapper_carries_theme_root_class(self) -> None:
        with render_isolated():
            html = serialize(Code("x = 1").render())
        assert "bz-code" in html
        assert "font-mono" in html

    def test_python_highlight_emits_pygments_spans(self) -> None:
        with render_isolated():
            html = serialize(Code("import os").render())
        # Pygments wraps tokens in ``<span class="...">``. The keyword
        # ``import`` becomes class="kn" by default (kn = keyword-namespace).
        assert 'class="kn"' in html or 'class="k"' in html
        assert "import" in html

    def test_unknown_lang_falls_back_no_crash(self) -> None:
        with render_isolated():
            html = serialize(Code("blob", lang="this-does-not-exist").render())
        assert "<pre" in html
        assert "blob" in html

    def test_special_chars_escaped_in_highlight(self) -> None:
        # Pygments' HtmlFormatter escapes by default.
        with render_isolated():
            html = serialize(Code("x = '<script>'").render())
        assert "<script>" not in html
        assert "&lt;script&gt;" in html

    def test_empty_string_renders_empty_block(self) -> None:
        with render_isolated():
            html = serialize(Code("").render())
        assert "<pre" in html
        assert "</pre>" in html

    def test_classes_kwarg_appends_to_root(self) -> None:
        with render_isolated():
            html = serialize(Code("x", classes="ring-2").render())
        assert "bz-code" in html
        assert "ring-2" in html


class TestLangDefault:
    def test_default_lang_python(self) -> None:
        # ``def`` is a Python keyword ; the default lang should colour
        # it through Pygments.
        with render_isolated():
            html = serialize(Code("def f(): pass").render())
        assert 'class="k"' in html  # keyword span around ``def``

    def test_html_lang_colours_tags(self) -> None:
        with render_isolated():
            html = serialize(Code("<div>x</div>", lang="html").render())
        # Tag name colour class (Pygments default style: ``nt``).
        assert 'class="nt"' in html


class TestReactiveText:
    def test_client_binding_emits_bz_text(self) -> None:
        from bretzel.state import ClientState, field
        from bretzel.state.scopes.client import rendering_scope

        class _CodeClient(ClientState, persist="memory"):
            snippet: str = field(default="x = 1")

        with render_isolated(), rendering_scope():
            state = _CodeClient()
            html = serialize(Code(state.snippet).render())
        assert 'bz-text="$bz.state._CodeClient.default.snippet"' in html
        # No Pygments spans on the reactive path.
        assert 'class="k"' not in html

    def test_client_expression_uses_full_path(self) -> None:
        from bretzel.state.scopes.client import ClientExpression

        expr = ClientExpression('$bz.state.MyState.default.code')
        with render_isolated():
            html = serialize(Code(expr).render())
        assert '$bz.state.MyState.default.code' in html
        assert "bz-text=" in html


class TestComponentTextRejected:
    def test_component_raises(self) -> None:
        # ``text=`` is the source Pygments highlights, not a generic
        # content slot -- unlike most components, Code does NOT honour
        # the universal str | Component | ClientBinding slot contract.
        # A Component used to be silently str()'d (its Python repr)
        # and syntax-highlighted as nonsense. Same bug class as
        # Markdown's ClientBinding rejection.
        import pytest

        from bretzel.components.base import ComponentUsageError
        from bretzel.components.primitives.text import Text

        with render_isolated():
            with pytest.raises(ComponentUsageError, match="Component"):
                Code(Text("hello"))
