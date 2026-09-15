"""Smoke tests for :class:`LineChart`."""

from __future__ import annotations

import json

from bretzel.components.base.testing import render_isolated
from bretzel.components.charts.line_chart.line_chart import LineChart
from bretzel.components.charts.series import Series
from bretzel.core.serialize import serialize


SAMPLE = [(0, 5), (1, 12), (2, 7), (3, 15), (4, 9), (5, 18)]


class TestLineChart:
    def test_default_emits_wrapper_with_svg(self) -> None:
        with render_isolated():
            out = serialize(LineChart(SAMPLE).render())
        assert out.startswith("<div")
        assert "<svg" in out
        assert 'role="img"' in out

    def test_single_series_uses_line_scope(self) -> None:
        # Unified hover : single-series rides the SAME ``lineScope`` as
        # multi (full-column hit detection), just ``n_series: 1``. No
        # more per-point ``tooltipScope`` — hover anywhere in the column.
        with render_isolated():
            out = serialize(LineChart(SAMPLE).render())
        assert "$bz.charts.lineScope({n_series: 1})" in out
        assert "tooltipScope" not in out

    def test_multi_series_uses_line_scope_with_n_series(self) -> None:
        from bretzel.components.charts.series import Series
        series = [
            Series(name="A", data=[(0, 1), (1, 2)]),
            Series(name="B", data=[(0, 3), (1, 4)]),
        ]
        with render_isolated():
            out = serialize(LineChart(series).render())
        # Multi-series keeps ``lineScope`` for the legend toggle +
        # ``active`` panel breakdown.
        assert "$bz.charts.lineScope({n_series:" in out

    def test_legend_items_carry_toggle_handlers(self) -> None:
        from bretzel.components.charts.series import Series
        series = [
            Series(name="A", data=[(0, 1), (1, 2)]),
            Series(name="B", data=[(0, 3), (1, 4)]),
        ]
        with render_isolated():
            out = serialize(LineChart(series).render())
        # Each legend ``<button>`` flips the series visibility (V3
        # bz-on:click, dim via bz-class MERGE, a11y via bz-attr).
        assert "toggleSeries(0)" in out
        assert "toggleSeries(1)" in out
        assert 'bz-on:click="$event.preventDefault(); toggleSeries(0)"' in out
        assert "bz-class=" in out
        assert "bz-attr:aria-pressed=" in out
        # Series paths react to the visibility state (V3 bz-show).
        assert 'bz-show="isVisible(0)"' in out
        assert 'bz-show="isVisible(1)"' in out

    def test_single_series_skips_visibility_plumbing(self) -> None:
        with render_isolated():
            out = serialize(LineChart(SAMPLE).render())
        # No reason to thread ``isVisible`` on a single-series chart
        # (there's no legend either).
        assert "isVisible(" not in out
        assert "toggleSeries(" not in out

    def test_emits_one_line_path_per_series(self) -> None:
        with render_isolated():
            out = serialize(LineChart(SAMPLE).render())
        # 1 line path + crosshair line + axis line + per-tick grid lines.
        assert "<path" in out
        assert ' d="M' in out

    def test_smooth_emits_bezier(self) -> None:
        with render_isolated():
            out = serialize(LineChart(SAMPLE, smooth=True).render())
        assert "C" in out

    def test_smooth_is_default(self) -> None:
        with render_isolated():
            default = serialize(LineChart(SAMPLE).render())
            sharp = serialize(LineChart(SAMPLE, smooth=False).render())
        # Smooth default emits a Catmull-Rom path (cubic Béziers).
        # Look for the ``C`` Bézier command inside a path's ``d=``
        # attribute — anchoring on the leading ``"d="`` keeps the
        # check robust against the word ``currentColor`` appearing
        # elsewhere (drop-shadow filter on the dot, etc.).
        import re
        def _has_bezier(html: str) -> bool:
            for m in re.finditer(r' d="([^"]+)"', html):
                if "C" in m.group(1):
                    return True
            return False
        assert _has_bezier(default)
        assert not _has_bezier(sharp)

    def test_area_fill_emits_two_paths_per_series(self) -> None:
        with render_isolated():
            plain = serialize(LineChart(SAMPLE).render())
            with_area = serialize(LineChart(SAMPLE, area_fill=True).render())
        assert with_area.count("<path") > plain.count("<path")

    def test_show_dots_emits_circle_per_point(self) -> None:
        with render_isolated():
            out = serialize(LineChart(SAMPLE, show_dots=True).render())
        # 6 dots per series + 1 marker per series (always present, hidden).
        assert out.count("<circle") >= 6

    def test_crosshair_present(self) -> None:
        # A vertical crosshair line marks the active column — bound to
        # ``active`` via bz-attr, dashed, hidden until hovered. This is
        # the fix for "je ne vois pas les points" : it connects the
        # per-series active dots into one readable slice.
        with render_isolated():
            out = serialize(LineChart(SAMPLE).render())
        assert 'class="stroke-text/20"' in out
        assert 'stroke-dasharray="4 4"' in out
        # Bound to the active column (``>`` is HTML-escaped in attrs).
        assert "bz-attr:x1=" in out
        assert "[active]" in out

    def test_active_dot_per_series(self) -> None:
        # One subtle "you are here" dot per series, bound to the
        # lineScope's ``active`` index ; xs/ys arrays baked verbatim
        # into the Alpine expression so the binding is hermetic.
        series = [
            Series(name="A", data=[(0, 1), (1, 2), (2, 3)]),
            Series(name="B", data=[(0, 4), (1, 5), (2, 6)]),
        ]
        with render_isolated():
            out = serialize(LineChart(series, show_dots=False).render())
        # V3 attr binds : one bz-attr:cy per series active dot.
        assert out.count("bz-attr:cy=") == 2
        # The active dots ride a literal-array index, not a scope
        # method call — sidesteps any init / scope-lookup timing.
        assert "[active]" in out
        # Active dots start hidden (active=-1) → display:none pre-stamp.
        assert "display:none" in out

    def test_single_series_uses_full_column_hit_rects(self) -> None:
        # Unified hover : single-series rides the SAME full-column hit
        # rects as multi (hover anywhere in the column — no landing on
        # the line). Each rect carries the point's display string + the
        # data-x anchor fraction the floating tooltip reads.
        with render_isolated():
            out = serialize(LineChart(SAMPLE).render())
        # 6 data points → 6 hit rects driving ``onHover($event, i)``.
        assert out.count("onHover($event,") == 6
        assert out.count('bz-on:mouseleave="onLeave()"') == 6
        # Display string + anchor fraction ride each rect.
        assert out.count("data-bz-display=") == 6
        assert out.count("data-bz-anchor-x=") == 6
        # No per-point ``show($event)`` hover circles anymore.
        assert "show($event)" not in out

    def test_multi_series_uses_hit_rects_and_following_tooltip(self) -> None:
        from bretzel.components.charts.series import Series
        series = [
            Series(name="A", data=[(0, 1), (1, 2), (2, 3)]),
            Series(name="B", data=[(0, 4), (1, 5), (2, 6)]),
        ]
        with render_isolated():
            out = serialize(LineChart(series).render())
        # 3 data indices → 3 hit-rect overlays driving ``onHover``.
        assert out.count("onHover($event,") == 3
        # No fixed-corner panel anymore — the value rides the shared
        # floating tooltip (runtime slab), so no ``bz-text`` binding.
        assert "bz-text=" not in out
        # The breakdown displays ride ``data-bz-display`` on the rects.
        assert 'A:' in out and 'B:' in out

    def test_empty_data_renders_no_data_placeholder(self) -> None:
        """L'état vide est un ``ui.empty_state``, pas un ``<text>`` SVG.

        Les quatre charts n'offraient que ``empty_text`` quand table,
        datatable et diagram offrent les quatre props — trois
        profondeurs pour un même besoin (audit § 1.3). Ils composent
        désormais le même ``EmptyState``, donc l'icône arrive.

        L'``aria-label`` reste vérifié : c'est le correctif F24, un
        chart vide doit annoncer SON identité et pas celle du voisin
        dont il a emprunté l'helper.
        """
        with render_isolated():
            out = serialize(LineChart([]).render())
        assert "<rect" not in out
        assert "No data" in out
        assert "line-chart" in out
        assert 'aria-label="Line chart — No data"' in out

    def test_list_of_numbers_uses_index_as_x(self) -> None:
        with render_isolated():
            out = serialize(LineChart([5, 8, 3, 12, 6]).render())
        assert "<path" in out

    def test_color_threads_into_line_stroke(self) -> None:
        with render_isolated():
            out = serialize(LineChart(SAMPLE, color="success").render())
        assert "stroke-(--bz-solid)" in out
        assert "bz-c-success" in out

    def test_size_drives_height(self) -> None:
        with render_isolated():
            xs = serialize(LineChart(SAMPLE, size="xs").render())
            xl = serialize(LineChart(SAMPLE, size="xl").render())
        assert 'height="140"' in xs
        assert 'height="440"' in xl

    def test_multi_series_emits_legend(self) -> None:
        series = [
            Series(name="2024", data=[(0, 1), (1, 2)]),
            Series(name="2025", data=[(0, 3), (1, 4)]),
        ]
        with render_isolated():
            out = serialize(LineChart(series).render())
        assert "2024" in out
        assert "2025" in out

    def test_multi_series_palette_cycles(self) -> None:
        series = [
            Series(name="A", data=[(0, 1)]),
            Series(name="B", data=[(0, 2)]),
            Series(name="C", data=[(0, 3)]),
        ]
        with render_isolated():
            out = serialize(LineChart(series).render())
        assert "stroke-(--bz-solid)" in out
        assert "bz-c-primary" in out
        assert "bz-c-success" in out
        assert "bz-c-warning" in out

    def test_multi_series_with_mismatched_x_raises(self) -> None:
        import pytest
        series = [
            Series(name="A", data=[(0, 1), (1, 2)]),
            Series(name="B", data=[(0, 3), (5, 4)]),  # mismatched x
        ]
        with render_isolated():
            with pytest.raises(ValueError, match="same x values"):
                LineChart(series).render()

    def test_y_format_currency_in_tooltip_displays(self) -> None:
        with render_isolated():
            out = serialize(LineChart(SAMPLE, y_format="currency").render())
        # Server-formatted displays land in each hit rect's
        # ``data-bz-display``.
        assert "$" in out
        assert "data-bz-display=" in out

    def test_no_bindable_props(self) -> None:
        assert LineChart.BINDABLE_PROPS == ()

    def test_reference_lines_render_threshold_and_label(self) -> None:
        from bretzel.components.charts.reference import Reference
        with render_isolated():
            out = serialize(LineChart(
                SAMPLE,
                reference_lines=[Reference(value=10, label="Goal",
                                           color="success")],
            ).render())
        # Refs ride in a dedicated ``<g class="bz-line-refs">`` so
        # they sit behind the data paths (z-order from SVG document
        # order).
        assert "bz-line-refs" in out
        assert ">Goal" in out
        # Numeric value is appended in parens for context.
        assert "(10)" in out
        # The custom colour wins over the muted fallback.
        assert "stroke-(--bz-solid)" in out
        assert "bz-c-success" in out

    def test_date_axis_auto_detects_daily_data(self) -> None:
        from datetime import date, timedelta
        data = [(date(2026, 1, 1) + timedelta(days=i), 50 + i)
                for i in range(30)]
        with render_isolated():
            out = serialize(LineChart(data).render())
        # 30-day span → "Mon DD" formatter ; tick text should include
        # named months from January.
        assert "Jan 01" in out

    def test_date_axis_auto_detects_intraday_data(self) -> None:
        from datetime import datetime
        data = [(datetime(2026, 1, 1, h, 0), 10 + h) for h in range(24)]
        with render_isolated():
            out = serialize(LineChart(data).render())
        # Sub-day span → "HH:MM" formatter.
        assert "00:00" in out or "12:00" in out

    def test_explicit_x_format_wins_over_date_auto_detect(self) -> None:
        from datetime import date
        data = [(date(2026, 1, i + 1), i) for i in range(5)]
        with render_isolated():
            out = serialize(
                LineChart(data, x_format=lambda x: f"D{x.day}").render()
            )
        # Le callable de l'appelant gagne, et il reçoit un ``datetime`` —
        # plus le timestamp POSIX de la mise à l'échelle, qui l'obligeait
        # à refaire ``fromtimestamp`` lui-même pour formater quoi que ce
        # soit (finding [11]). Sur un axe NUMÉRIQUE il reçoit toujours le
        # nombre : c'est la détection de date qui décide.
        assert ">D" in out

    def test_reference_lines_accept_tuple_shorthand(self) -> None:
        with render_isolated():
            out = serialize(LineChart(
                SAMPLE,
                reference_lines=[(8, "Baseline"), (15, "Target", "warning")],
            ).render())
        assert ">Baseline" in out
        assert ">Target" in out
        # Bare 2-tuple falls back to ``muted`` ; 3-tuple uses explicit colour.
        assert "stroke-(--bz-solid)" in out
        assert "bz-c-muted" in out
        assert "bz-c-warning" in out

    def test_show_axis_false_drops_y_axis_line(self) -> None:
        with render_isolated():
            on = serialize(LineChart(SAMPLE, show_axis=True).render())
            off = serialize(LineChart(SAMPLE, show_axis=False,
                                      show_gridlines=False).render())
        assert on.count("<line") > off.count("<line")

    def test_x_ticks_clamped_to_data_domain(self) -> None:
        # compute_ticks(0, 11) returns [0, 5, 10, 15] — the 15 used to
        # render past plot_right as an orphan x-label. The filter in
        # _render_x_axis_labels keeps only ticks inside [xmin, xmax].
        # Y stays in a small range so the y-axis can't add a "15" label
        # back via its own (snapped) tick bracket.
        from bretzel.components.charts.line_chart.line_chart import (
            _render_x_axis_labels,
        )
        ticks_html_in = _render_x_axis_labels(
            slot=lambda _name: "",
            xmin=0, xmax=11, x_scale=lambda v: v,
            plot_bottom=200, axis_font=12, x_format=None,
        )
        from bretzel.core.serialize import serialize as _ser
        rendered = _ser(ticks_html_in)
        assert ">15<" not in rendered
        assert ">10<" in rendered
