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


class TestTheLineIsTheFrameworkBorder:
    """The line was a 1 px box ``bg-current opacity-20`` in the muted text
    colour — about three times the contrast of the borders around it, so
    next to a sidebar's edge it read as a thicker line (Orga,
    2026-11-12). It is now a border, in the framework's border tint and
    stroke width."""

    def _line(self, **kwargs):
        with render_isolated():
            return Divider(**kwargs).render().children[0].attrs["class"].split()

    def test_the_neutral_line_is_the_sidebar_edge(self) -> None:
        from bretzel.components.navigation.sidebar.theme import SIDEBAR_THEME

        line = self._line()
        assert "border-line" in line
        assert "border-line" in str(SIDEBAR_THEME["slots"]["root"])
        assert "border-t-(length:--bz-stroke)" in line
        assert not [c for c in line if c.startswith(("bg-", "opacity-"))]

    def test_a_vertical_line_is_the_same_border(self) -> None:
        line = self._line(orientation="vertical")
        assert "border-line" in line
        assert "border-l-(length:--bz-stroke)" in line

    def test_a_colour_draws_its_border_step(self) -> None:
        line = self._line(color="primary")
        assert "border-(--bz-border)" in line
        assert "border-line" not in line


class TestGap:
    """``gap=`` : l'espace de chaque côté du trait, les pas de tout ``gap``."""

    def _root_class(self, **kw) -> str:
        import re

        from bretzel import ui
        from bretzel.components.base.testing import render_isolated
        from bretzel.core.serialize import serialize
        with render_isolated():
            html = serialize(ui.divider(**kw).render())
        return re.search(r'class="([^"]*)"', html).group(1)

    def test_the_default_is_the_space_it_always_had(self) -> None:
        assert "my-(--bz-gap-2)" in self._root_class().split()

    def test_none_draws_the_line_flush(self) -> None:
        assert "my-0" in self._root_class(gap="none").split()

    def test_a_vertical_divider_spaces_across_its_line(self) -> None:
        classes = self._root_class(orientation="vertical", gap="lg").split()
        assert "mx-(--bz-gap-6)" in classes
        assert not [c for c in classes if c.startswith("my-")]

    def test_a_step_off_the_scale_is_refused(self) -> None:
        import pytest

        from bretzel import ui
        from bretzel.components.base.attrs import ComponentUsageError
        from bretzel.components.base.testing import render_isolated
        with render_isolated(), pytest.raises(ComponentUsageError):
            ui.divider(gap="huge").render()
