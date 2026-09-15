"""Smoke tests for :class:`Sparkline`."""

from __future__ import annotations

from bretzel.components.base.testing import render_isolated
from bretzel.components.charts.sparkline.sparkline import Sparkline
from bretzel.core.serialize import serialize


class TestSparkline:
    def test_default_emits_svg(self) -> None:
        with render_isolated():
            out = serialize(Sparkline([1, 2, 3, 4, 5]).render())
        assert out.startswith("<svg")
        assert 'role="img"' in out
        assert "viewBox=" in out

    def test_emits_polyline_path(self) -> None:
        with render_isolated():
            out = serialize(Sparkline([0, 10, 5, 8, 12]).render())
        assert "<path" in out
        assert ' d="M' in out  # path data starts with M (moveto)

    def test_empty_data_renders_empty_svg(self) -> None:
        # Empty payload : the SVG renders, but with no <path> inside.
        # Sparkline is decorative, so we don't raise — the empty box
        # silently disappears next to whatever consumer renders.
        with render_isolated():
            out = serialize(Sparkline([]).render())
        assert out.startswith("<svg")
        assert "<path" not in out
        # The aria summary reports the empty state.
        assert "no data" in out.lower()

    def test_smooth_variant_emits_bezier(self) -> None:
        with render_isolated():
            out = serialize(
                Sparkline([1, 5, 3, 8, 4, 9], smooth=True).render()
            )
        # Catmull-Rom-as-Bézier path → contains "C" for cubic segments.
        assert "C" in out

    def test_area_fill_emits_two_paths(self) -> None:
        with render_isolated():
            out = serialize(
                Sparkline([1, 2, 3, 4, 5], area_fill=True).render()
            )
        assert out.count("<path") == 2  # area + line

    def test_show_last_dot_emits_circle(self) -> None:
        with render_isolated():
            out = serialize(
                Sparkline([1, 2, 3], show_last_dot=True).render()
            )
        assert "<circle" in out

    def test_color_threads_into_theme_classes(self) -> None:
        with render_isolated():
            out = serialize(
                Sparkline([1, 2, 3], color="success").render()
            )
        assert "stroke-(--bz-solid)" in out
        assert "bz-c-success" in out

    def test_size_drives_svg_height(self) -> None:
        with render_isolated():
            xs = serialize(Sparkline([1, 2, 3], size="xs").render())
            xl = serialize(Sparkline([1, 2, 3], size="xl").render())
        assert 'height="16"' in xs
        assert 'height="64"' in xl

    def test_width_kwarg_threads_into_svg(self) -> None:
        with render_isolated():
            out = serialize(Sparkline([1, 2, 3], width=240).render())
        assert 'width="240"' in out

    def test_tuple_data_shape_accepted(self) -> None:
        with render_isolated():
            out = serialize(
                Sparkline([(0, 5), (1, 10), (2, 7)]).render()
            )
        assert "<path" in out

    def test_no_bindable_props(self) -> None:
        assert Sparkline.BINDABLE_PROPS == ()

    def test_aria_summary_reports_extrema(self) -> None:
        with render_isolated():
            out = serialize(Sparkline([3, 1, 8, 4]).render())
        assert "min 1" in out
        assert "max 8" in out

    def test_constant_series_renders_flat_line(self) -> None:
        # Degenerate y-domain → scale collapses to midpoint, line
        # renders as a horizontal stroke.
        with render_isolated():
            out = serialize(Sparkline([5, 5, 5, 5]).render())
        assert "<path" in out
