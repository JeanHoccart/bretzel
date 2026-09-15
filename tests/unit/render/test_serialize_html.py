"""Unit tests for :func:`bretzel.render.serialize_html`."""

from __future__ import annotations

from bretzel.components.base.testing import render_isolated
from bretzel.components.primitives.text import Text
from bretzel.render import serialize_html


class TestSerializeHtml:
    def test_returns_string(self) -> None:
        with render_isolated():
            html = serialize_html(Text("Hello"))
        assert isinstance(html, str)

    def test_wraps_in_default_tag(self) -> None:
        with render_isolated():
            html = serialize_html(Text("Hello"))
        assert "<span" in html
        assert ">Hello<" in html

    def test_escapes_special_chars(self) -> None:
        with render_isolated():
            html = serialize_html(Text("<script>"))
        assert "<script>" not in html
        assert "&lt;script&gt;" in html


class TestDetachFromParent:
    def test_serialize_html_does_not_leave_phantom_child(self) -> None:
        """``serialize_html(ui.button(...))`` from inside a ``with``
        block must not leave the button registered as a phantom child
        of the parent — otherwise the parent renders the button twice.
        """
        from bretzel.components.actions.button import Button
        from bretzel.components.layout.stack import VStack

        with render_isolated():
            with VStack() as stack:
                serialize_html(Button("Inspect me"))
            assert stack._children == []

    def test_serialize_html_renders_in_render_mode(self) -> None:
        """``serialize_html`` must enter render-mode around ``render()``.

        A Component built INSIDE the target's ``render()`` (a × button's
        Icon, a chevron…) auto-registers with the active parent unless
        the context is in render-mode. ``_render_children`` sets that flag
        during the normal walk ; ``serialize_html`` calls ``render()``
        directly, so it must set it too — otherwise the inner child leaks
        onto ``root_children`` and paints a 2ⁿ time, orphaned, in the page
        that called ``serialize_html`` (the playground × bug, 2026-07-18).

        Uses a deliberately UN-defended component (no ``render_detached``)
        so the test pins the ``serialize_html`` contract itself, not a
        given component's per-site defense.
        """
        from bretzel.components.base.component import Component
        from bretzel.components.primitives.icon import Icon
        from bretzel.core.tree import Element

        class _Leaky(Component):
            DEFAULT_TAG = "div"

            def render(self) -> Element:
                # Construit un Icon dans render() SANS detach — fuit si le
                # caller n'est pas en render-mode.
                return Element(
                    tag="div", attrs={},
                    children=(Icon("x", size="sm").render(),),
                )

        with render_isolated() as ctx:
            before = len(ctx.root_children)
            serialize_html(_Leaky())
            assert len(ctx.root_children) == before, (
                "serialize_html a laissé un enfant construit dans render() "
                "fuir sur root_children → il faut rendre en render-mode "
                "(ctx.is_rendering) comme _render_children."
            )


class TestShellPygmentsStyle:
    def test_default_shell_carries_pygments_style(self) -> None:
        from bretzel.render.shell import default_shell

        html = default_shell(
            body_html="<p>hi</p>",
            envelope_json="{}",
            page_uuid="test",
        )
        assert ".bz-code" in html
        # A representative Pygments class : ``.k`` (keyword) is in the
        # default style.
        assert ".bz-code .k" in html
