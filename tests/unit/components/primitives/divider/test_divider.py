"""Smoke tests for :class:`Divider` — separator with optional label."""

from __future__ import annotations

from bretzel.components.base.testing import render_isolated
from bretzel.components.primitives.divider.divider import Divider
from bretzel.core.serialize import serialize
from bretzel.state import ClientState, field
from bretzel.state.scopes.client import rendering_scope


class _DividerState(ClientState):
    label: str = field(default="OR")


class TestDivider:
    def test_default_horizontal(self) -> None:
        with render_isolated():
            out = serialize(Divider().render())
        assert 'role="separator"' in out
        assert 'aria-orientation="horizontal"' in out

    def test_vertical_orientation(self) -> None:
        with render_isolated():
            out = serialize(Divider(orientation="vertical").render())
        assert 'aria-orientation="vertical"' in out

    def test_no_label_renders_single_line(self) -> None:
        """Without a label, the divider is one line element only."""
        with render_isolated():
            rendered = Divider().render()
        # One child : the line div.
        assert len(rendered.children) == 1

    def test_label_renders_line_label_line(self) -> None:
        """``[line, label, line]`` — two flanking line elements when a
        label is set so the rule visually breaks for the text."""
        with render_isolated():
            rendered = Divider(label="OR").render()
            out = serialize(rendered)
        assert ">OR<" in out
        # Exactly 3 children : line, label span, line.
        assert len(rendered.children) == 3

    def test_color_propagates_to_root(self) -> None:
        with render_isolated():
            out = serialize(Divider(color="primary").render())
        assert "text-(--bz-text)" in out
        assert "bz-c-primary" in out

    def test_label_binding_renders_reactive_text(self) -> None:
        with render_isolated(), rendering_scope():
            rendered = Divider(label=_DividerState().label).render()
            out = serialize(rendered)
        assert len(rendered.children) == 3
        assert 'bz-text="$bz.state._DividerState.default.label"' in out
