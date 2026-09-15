"""Unit tests for :class:`bretzel.components.layout.grid.Grid`."""

from __future__ import annotations

import pytest

from bretzel.components.base.attrs import ComponentUsageError
from bretzel.components.base.testing import render_isolated
from bretzel.components.layout.grid import Grid
from bretzel.components.primitives.text import Text
from bretzel.core.serialize import serialize


class TestDefaults:
    def test_default_render_is_bare_grid(self) -> None:
        with render_isolated():
            g = Grid()
        out = serialize(g.render())
        # Root carries the ``grid`` class + the default gap (md).
        assert "grid" in out
        assert "gap-4" in out
        # No cols= → no grid-cols-* class is emitted.
        assert "grid-cols-" not in out
        assert out.startswith("<div")


class TestCols:
    @pytest.mark.parametrize("n", [1, 2, 3, 4, 6, 12])
    def test_cols_int(self, n: int) -> None:
        with render_isolated():
            g = Grid(cols=n)
        out = serialize(g.render())
        assert f"grid-cols-{n}" in out

    def test_cols_dict_responsive(self) -> None:
        with render_isolated():
            g = Grid(cols={"base": 1, "sm": 2, "md": 3, "lg": 4})
        out = serialize(g.render())
        # ``base`` keys emit unprefixed.
        assert "grid-cols-1" in out
        assert "sm:grid-cols-2" in out
        assert "md:grid-cols-3" in out
        assert "lg:grid-cols-4" in out

    def test_cols_dict_xs_alias_emits_unprefixed(self) -> None:
        # ``xs`` is treated like ``base`` (no breakpoint prefix) so
        # the column count applies at every viewport size up to the
        # next override.
        with render_isolated():
            g = Grid(cols={"xs": 1, "md": 3})
        out = serialize(g.render())
        assert "grid-cols-1" in out
        assert "md:grid-cols-3" in out
        # No ``xs:`` prefix leaks through.
        assert "xs:grid-cols" not in out

    @pytest.mark.parametrize(
        ("token", "expected"),
        [("none", "grid-cols-none"), ("auto", "grid-cols-auto")],
    )
    def test_cols_string_keyword(self, token: str, expected: str) -> None:
        with render_isolated():
            g = Grid(cols=token)
        assert expected in serialize(g.render())

    def test_cols_string_passthrough_for_raw_tailwind(self) -> None:
        # Arbitrary class strings flow through verbatim — the escape
        # hatch for fixed-track layouts like ``grid-cols-[200px_1fr]``.
        with render_isolated():
            g = Grid(cols="grid-cols-[200px_1fr]")
        assert "grid-cols-[200px_1fr]" in serialize(g.render())


class TestGap:
    @pytest.mark.parametrize(
        ("gap", "expected"),
        [
            ("none", "gap-0"),
            ("xs",   "gap-1"),
            ("sm",   "gap-2"),
            ("md",   "gap-4"),
            ("lg",   "gap-6"),
            ("xl",   "gap-8"),
        ],
    )
    def test_gap(self, gap: str, expected: str) -> None:
        with render_isolated():
            g = Grid(gap=gap)
        assert expected in serialize(g.render())


class TestChildrenAndEscape:
    def test_with_block_collects_children(self) -> None:
        with render_isolated(), Grid(cols=2) as g:
            Text("a")
            Text("b")
            Text("c")
        out = serialize(g.render())
        for word in ("a", "b", "c"):
            assert f">{word}<" in out
        # The grid wrapper appears once.
        assert out.count("grid-cols-2") == 1

    def test_user_classes_appended(self) -> None:
        with render_isolated():
            g = Grid(cols=3, classes="my-extra")
        assert "my-extra" in serialize(g.render())

    def test_no_identity_attrs_when_static(self) -> None:
        with render_isolated():
            g = Grid(cols=3)
        out = serialize(g.render())
        assert "bz-id" not in out
        assert "bz-version" not in out


class TestGapResponsive:
    """``gap`` is graded like ``cols``, so it takes the same dict — and
    both go through the one shared parser in ``base/responsive.py``."""

    def test_gap_dict_prefixes_each_breakpoint(self) -> None:
        with render_isolated():
            g = Grid(gap={"base": "sm", "md": "lg"})
        out = serialize(g.render())
        assert "gap-2" in out
        assert "md:gap-6" in out

    def test_cols_and_gap_dicts_together(self) -> None:
        with render_isolated():
            g = Grid(cols={"base": 1, "md": 3}, gap={"base": "sm", "md": "lg"})
        out = serialize(g.render())
        for expected in ("grid-cols-1", "md:grid-cols-3", "gap-2", "md:gap-6"):
            assert expected in out

    def test_scalar_gap_still_works(self) -> None:
        with render_isolated():
            g = Grid(cols=4, gap="lg")
        out = serialize(g.render())
        assert "grid-cols-4" in out
        assert "gap-6" in out

    def test_unknown_breakpoint_is_refused(self) -> None:
        with render_isolated():
            g = Grid(cols={"base": 1, "phone": 2})
            with pytest.raises(ComponentUsageError, match="unknown breakpoint"):
                g.render()
