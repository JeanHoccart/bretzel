"""Unit tests for reactive content on the Heading component."""

from __future__ import annotations

from bretzel.components.base.testing import render_isolated
from bretzel.components.primitives.heading import Heading
from bretzel.core.serialize import serialize
from bretzel.state import ClientState, field
from bretzel.state.scopes.client import rendering_scope


class _TitleState(ClientState, persist="memory"):
    title: str = field(default="My page")


class TestStaticHeading:
    def test_literal_content_emits_text_node(self) -> None:
        with render_isolated():
            h = Heading("Hello", level=2)
        out = serialize(h.render())
        assert ">Hello<" in out
        assert "bz-text" not in out


class TestReactiveHeading:
    def test_binding_content_emits_bz_text_span(self) -> None:
        with render_isolated(), rendering_scope():
            state = _TitleState()
            h = Heading(state.title, level=2)
        out = serialize(h.render())
        # The wrapper span lives INSIDE the <h2> ; the bound path
        # drives bz-text.
        assert 'bz-text="$bz.state._TitleState.default.title"' in out
        # No raw SSR text node.
        assert ">My page<" not in out


class TestComponentContent:
    """Heading.content accepts a Component (universal contract)."""

    def test_component_content_renders_inner(self) -> None:
        from bretzel.components.primitives.icon import Icon

        with render_isolated():
            h = Heading(Icon("star"), level=2)
        out = serialize(h.render())
        assert "iconify-icon" in out
        assert "object at 0x" not in out

    def test_component_content_detached_from_parent(self) -> None:
        from bretzel.components.layout.stack import VStack
        from bretzel.components.primitives.icon import Icon

        with render_isolated():
            with VStack() as stack:
                Heading(Icon("star"), level=2)
            assert len(stack._children) == 1
            assert isinstance(stack._children[0], Heading)
