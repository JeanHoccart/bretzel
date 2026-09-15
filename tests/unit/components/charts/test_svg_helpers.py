"""Pure-function tests for :mod:`bretzel.components.charts._svg`.

These helpers don't touch the component machinery — they're just
math + string. Testing them in isolation pins the visual contract
each chart depends on.
"""

from __future__ import annotations

import math

import pytest

from bretzel.components.charts._svg import (
    arc_path,
    area_path,
    compute_ticks,
    format_value,
    line_path,
    linear_scale,
    nice_domain,
    smooth_path,
)


class TestLinearScale:
    def test_maps_endpoints_exactly(self) -> None:
        scale = linear_scale(0, 100, 0, 200)
        assert scale(0) == 0
        assert scale(100) == 200

    def test_interpolates_midpoint(self) -> None:
        scale = linear_scale(0, 10, 0, 100)
        assert scale(5) == 50

    def test_inverts_range_when_needed(self) -> None:
        # SVG y grows downward — typical chart use case flips data→pixel.
        scale = linear_scale(0, 100, 200, 0)
        assert scale(0) == 200
        assert scale(100) == 0

    def test_degenerate_domain_collapses_to_midpoint(self) -> None:
        scale = linear_scale(5, 5, 0, 100)
        assert scale(5) == 50
        assert scale(0) == 50  # any input collapses


class TestNiceDomain:
    def test_empty_returns_unit_interval(self) -> None:
        assert nice_domain([]) == (0.0, 1.0)

    def test_single_value_adds_padding(self) -> None:
        lo, hi = nice_domain([42])
        assert lo < 42 < hi

    def test_typical_series_pads_5_percent(self) -> None:
        lo, hi = nice_domain([0, 100])
        # 5 % of span = 5 ; but the lower bound is clamped at 0.
        assert lo == 0
        assert hi == 105

    def test_padded_negative_domain_does_not_cross_zero(self) -> None:
        # All-negative data → the upper pad is allowed up to (but not
        # past) zero. Snapping the baseline to zero is the chart's job,
        # not the domain helper's.
        lo, hi = nice_domain([-50, -10])
        assert hi <= 0
        assert lo < -50


class TestComputeTicks:
    def test_returns_round_numbers(self) -> None:
        ticks = compute_ticks(0, 100, target_count=5)
        # Contract : brackets the domain with target_count ± 2 ticks,
        # all values land on a "nice" power-of-10 step (1, 2 or 5).
        assert ticks[0] <= 0
        assert ticks[-1] >= 100
        assert 3 <= len(ticks) <= 8
        step = ticks[1] - ticks[0]
        magnitude = 10 ** math.floor(math.log10(step))
        assert step / magnitude in (1, 2, 5, 10)

    def test_handles_tiny_ranges(self) -> None:
        ticks = compute_ticks(0, 0.1, target_count=4)
        assert len(ticks) >= 2

    def test_degenerate_domain_returns_single_point(self) -> None:
        assert compute_ticks(5, 5, target_count=5) == [5]


class TestLinePath:
    def test_empty_returns_empty_string(self) -> None:
        assert line_path([]) == ""

    def test_single_point_emits_moveto(self) -> None:
        assert line_path([(10, 20)]) == "M10,20"

    def test_polyline_uses_M_then_L(self) -> None:
        assert line_path([(0, 0), (10, 5), (20, 0)]) == "M0,0L10,5L20,0"

    def test_rounds_to_two_decimals(self) -> None:
        # 1/3 ≈ 0.333… → "0.33".
        path = line_path([(1 / 3, 2 / 3)])
        assert "0.33" in path
        assert "0.67" in path


class TestSmoothPath:
    def test_two_points_falls_back_to_straight_line(self) -> None:
        # Catmull-Rom needs 3+ points ; two-point case mirrors line_path.
        assert smooth_path([(0, 0), (10, 10)]) == line_path([(0, 0), (10, 10)])

    def test_three_points_emits_bezier(self) -> None:
        path = smooth_path([(0, 0), (5, 5), (10, 0)])
        # Should contain at least one cubic Bézier segment.
        assert "C" in path
        # Starts at the first point.
        assert path.startswith("M0,0")


class TestAreaPath:
    def test_closes_to_baseline(self) -> None:
        path = area_path([(0, 5), (10, 0)], baseline_y=20)
        # Ends with a line back to the baseline and a Z closer.
        assert path.endswith("Z")
        assert "L10,20" in path  # drop to baseline at last x
        assert "L0,20" in path   # walk back along baseline


class TestFormatValue:
    def test_none_fallback_plain_int(self) -> None:
        assert format_value(42, None) == "42"

    def test_none_fallback_strips_trailing_zeros(self) -> None:
        assert format_value(3.10, None) == "3.1"
        assert format_value(3.00, None) == "3"

    def test_abbreviated_thousands(self) -> None:
        assert format_value(1234, "abbreviated") == "1.2k"
        assert format_value(2000, "abbreviated") == "2k"

    def test_abbreviated_millions_and_billions(self) -> None:
        assert format_value(2_500_000, "abbreviated") == "2.5M"
        assert format_value(3_000_000_000, "abbreviated") == "3B"

    def test_abbreviated_under_thousand_stays_plain(self) -> None:
        assert format_value(987, "abbreviated") == "987"

    def test_percent(self) -> None:
        assert format_value(0.42, "percent") == "42%"
        assert format_value(1, "percent") == "100%"

    def test_currency(self) -> None:
        assert format_value(1234.5, "currency") == "$1,234.50"

    def test_callable_wins(self) -> None:
        assert format_value(7, lambda v: f"#{v}") == "#7"

    def test_unit_suffix_appended(self) -> None:
        assert format_value(91.3, None, unit="ms") == "91.3 ms"
        assert format_value(1500, "abbreviated", unit="users") == "1.5k users"
        assert format_value(1200, "currency", unit="USD") == "$1,200.00 USD"

    def test_unit_skipped_on_percent(self) -> None:
        # ``%`` is already the unit ; appending anything else would
        # read as ``"42% req"`` — confusing.
        assert format_value(0.42, "percent", unit="req") == "42%"

    def test_unit_skipped_when_fmt_is_callable(self) -> None:
        # The callable owns the full output, including any unit.
        assert (
            format_value(7, lambda v: f"#{v} pts", unit="ms")
            == "#7 pts"
        )


class TestArcPath:
    def test_empty_arc_returns_empty(self) -> None:
        assert arc_path(0, 0, 50, 0, 0) == ""

    def test_pie_wedge_starts_and_ends_at_centre(self) -> None:
        path = arc_path(50, 50, 40, 0, math.pi / 2)
        # Pie wedge : moves to centre, lines out, arcs, closes with Z.
        assert path.startswith("M50,50")
        assert path.endswith("Z")
        assert "A40,40" in path  # arc with radius 40

    def test_donut_wedge_has_two_arcs(self) -> None:
        path = arc_path(50, 50, 40, 0, math.pi / 2, inner_radius=20)
        # Donut traces outer arc + inner arc back.
        assert path.count("A") == 2

    def test_full_circle_splits_into_two_arcs(self) -> None:
        # SVG can't draw a 360° arc in a single path — splitter must
        # produce two arcs in one return value.
        path = arc_path(50, 50, 40, 0, 2 * math.pi)
        assert path.count("A") >= 2

    def test_solid_full_circle_has_no_center_cut(self) -> None:
        # A 100 % solid pie (no donut) must NOT contain an ``L`` line
        # back to the centre — that's what created the visible seam
        # down the middle of single-slice pies. Single ``M`` (the
        # path's start), two semicircle arcs, ``Z`` to close.
        path = arc_path(50, 50, 40, 0, 2 * math.pi, inner_radius=0)
        assert "L" not in path
        assert path.count("M") == 1
        assert path.endswith("Z")

    def test_donut_full_circle_still_splits(self) -> None:
        # The split-and-merge path for full donuts is preserved (the
        # outer + inner halves still need separate sub-paths for the
        # fill rule to cut the hole correctly).
        path = arc_path(50, 50, 40, 0, 2 * math.pi, inner_radius=20)
        assert path.count("M") == 2
