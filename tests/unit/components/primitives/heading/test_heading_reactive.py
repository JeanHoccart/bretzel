"""Unit tests for reactive content on the Heading component."""

from __future__ import annotations

import pytest

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


class TestLevel:
    @pytest.mark.parametrize("level", [7, "2", "1><img src=x onerror=alert(1)><h1", True])
    def test_a_level_outside_one_to_six_is_refused(self, level) -> None:
        # ``level`` builds the tag (``h{level}``): a string was markup
        # (2026-11-06), a 7 an ``<h7>``.
        with render_isolated(), pytest.raises(ValueError, match="1 to 6"):
            Heading("t", level=level).render()

    @pytest.mark.parametrize("level", [1, 6])
    def test_one_to_six_are_headings(self, level: int) -> None:
        with render_isolated():
            out = serialize(Heading("t", level=level).render())
        assert out.startswith(f"<h{level}")
