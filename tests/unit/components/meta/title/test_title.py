"""Unit tests for :class:`Title` — page-level <title> override."""

from __future__ import annotations

import pytest

from bretzel.components.base.testing import render_isolated
from bretzel.components.meta.title.title import Title
from bretzel.core.serialize import serialize
from bretzel.core.tree import FragmentNode as FragmentNode
class TestTitleWritesContext:
    def test_writes_head_title_on_render(self) -> None:
        """The side-effect fires from ``render()``, not ``__init__`` —
        consistent with every other render-time effect in Bretzel."""
        with render_isolated() as ctx:
            t = Title("Dashboard")
            assert ctx.head_title is None
            t.render()
            assert ctx.head_title == "Dashboard"

    def test_last_call_wins(self) -> None:
        """A page that renders multiple ``ui.title()`` ends up with the
        deepest / latest one. Layout sets a fallback ; page overrides."""
        with render_isolated() as ctx:
            Title("Layout default").render()
            Title("Page-specific").render()
        assert ctx.head_title == "Page-specific"

    def test_empty_string_does_not_overwrite(self) -> None:
        """An accidental empty title is worse than no title at all —
        we keep whatever previous value (or fall through to the
        decorator default) instead of shipping ``<title></title>``."""
        with render_isolated() as ctx:
            Title("Real title").render()
            Title("").render()
        assert ctx.head_title == "Real title"


class TestTitleRender:
    def test_render_returns_empty_fragment(self) -> None:
        """The body must remain unchanged — Title only contributes to
        the document head."""
        with render_isolated():
            rendered = Title("Foo").render()
        assert isinstance(rendered, FragmentNode)
        assert rendered.children == ()

    def test_serializes_to_empty_string(self) -> None:
        with render_isolated():
            out = serialize(Title("Foo").render())
        assert out == ""


class TestTitleArgsValidation:
    def test_extra_kwargs_rejected(self) -> None:
        with render_isolated():
            with pytest.raises(TypeError, match="positional text argument"):
                Title("Foo", classes="hidden")  # type: ignore[call-arg]

    def test_non_string_text_rejected(self) -> None:
        with render_isolated():
            with pytest.raises(TypeError, match="must be a str"):
                Title(42)  # type: ignore[arg-type]


class TestTitleOutsideRenderScope:
    def test_render_outside_scope_raises(self) -> None:
        """Rendering a Title outside a render scope must surface
        clearly — otherwise the title silently vanishes into nowhere."""
        # Build the Title inside a scope so __init__ + auto-attach work,
        # then call render() outside the scope to hit the no-context path.
        with render_isolated():
            t = Title("Foo")
        # ``render_isolated`` exited — no context is active anymore.
        with pytest.raises(RuntimeError, match="render scope"):
            t.render()


class TestTitleSurface:
    def test_not_container(self) -> None:
        assert Title.IS_CONTAINER is False

    def test_no_bindable_props(self) -> None:
        assert Title.BINDABLE_PROPS == ()

    def test_no_events(self) -> None:
        assert Title.EVENTS == ()
