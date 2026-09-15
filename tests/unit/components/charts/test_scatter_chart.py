"""Smoke tests for :class:`ScatterChart`."""

from __future__ import annotations

from bretzel.components.base.testing import render_isolated
from bretzel.components.charts.reference import Reference
from bretzel.components.charts.scatter_chart.scatter_chart import ScatterChart
from bretzel.components.charts.series import Series
from bretzel.core.serialize import serialize


SAMPLE = [(1, 5), (2, 12), (3, 7), (4, 18), (5, 9), (6, 15)]


class TestScatterChart:
    def test_default_emits_wrapper_with_svg(self) -> None:
        with render_isolated():
            out = serialize(ScatterChart(SAMPLE).render())
        assert out.startswith("<div")
        assert "<svg" in out
        assert 'role="img"' in out

    def test_one_circle_per_data_point(self) -> None:
        with render_isolated():
            out = serialize(ScatterChart(SAMPLE).render())
        assert out.count("<circle") == 6

    def test_each_circle_carries_tooltip_payload(self) -> None:
        with render_isolated():
            out = serialize(ScatterChart(SAMPLE).render())
        assert out.count("data-bz-display") == 6
        # Pair appears in display.
        assert "(1, 5)" in out
        # Hover wiring is V3 bz-on, one pair per dot.
        assert out.count('bz-on:mouseenter="show($event)"') == 6
        assert out.count('bz-on:mouseleave="hide()"') == 6

    def test_scatter_scope_on_wrapper(self) -> None:
        with render_isolated():
            out = serialize(ScatterChart(SAMPLE).render())
        # V3 chart scope rides bz-data on the wrapper.
        assert 'bz-data="$bz.charts.scatterScope({n_series:' in out

    def test_color_threads_into_dot_fill(self) -> None:
        with render_isolated():
            out = serialize(ScatterChart(SAMPLE, color="success").render())
        assert "fill-(--bz-solid)" in out
        assert "bz-c-success" in out

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
            out = serialize(ScatterChart([]).render())
        assert "<rect" not in out
        assert "No data" in out
        assert "scatter-chart" in out
        assert 'aria-label="Scatter plot — No data"' in out

    def test_multi_series_independent_x_values(self) -> None:
        # Unlike LineChart, scatter doesn't require series to share x.
        series = [
            Series(name="A", data=[(0.1, 5), (0.5, 7), (1.2, 3)]),
            Series(name="B", data=[(2.3, 8), (3.0, 12)]),  # different x
        ]
        with render_isolated():
            out = serialize(ScatterChart(series).render())
        assert out.count("<circle") == 5
        assert "A" in out and "B" in out

    def test_multi_series_palette_cycles(self) -> None:
        series = [
            Series(name="A", data=[(0, 1)]),
            Series(name="B", data=[(0, 2)]),
            Series(name="C", data=[(0, 3)]),
        ]
        with render_isolated():
            out = serialize(ScatterChart(series).render())
        assert "fill-(--bz-solid)" in out
        assert "bz-c-primary" in out
        assert "bz-c-success" in out
        assert "bz-c-warning" in out

    def test_legend_toggle_handlers_on_multi_series(self) -> None:
        series = [
            Series(name="A", data=[(0, 1)]),
            Series(name="B", data=[(0, 2)]),
        ]
        with render_isolated():
            out = serialize(ScatterChart(series).render())
        assert "toggleSeries(0)" in out
        assert "toggleSeries(1)" in out
        # Legend buttons wire the toggle via V3 bz-on:click (shared
        # _render_legend with LineChart), dim via bz-class MERGE.
        assert 'bz-on:click="$event.preventDefault(); toggleSeries(0)"' in out
        assert "bz-class=" in out
        # Series groups react to the legend (V3 bz-show directive).
        assert 'bz-show="isVisible(0)"' in out

    def test_reference_lines_render_threshold(self) -> None:
        with render_isolated():
            out = serialize(ScatterChart(
                SAMPLE,
                reference_lines=[Reference(value=10, label="Threshold",
                                           color="warning")],
            ).render())
        assert "bz-line-refs" in out
        assert ">Threshold" in out
        assert "stroke-(--bz-solid)" in out
        assert "bz-c-warning" in out

    def test_size_drives_height(self) -> None:
        with render_isolated():
            xs = serialize(ScatterChart(SAMPLE, size="xs").render())
            xl = serialize(ScatterChart(SAMPLE, size="xl").render())
        assert 'height="140"' in xs
        assert 'height="440"' in xl

    def test_date_axis_auto_detect(self) -> None:
        from datetime import date, timedelta
        data = [(date(2026, 1, 1) + timedelta(days=i), i * 2)
                for i in range(30)]
        with render_isolated():
            out = serialize(ScatterChart(data).render())
        assert "Jan 01" in out

    def test_y_unit_threads_to_tooltip(self) -> None:
        with render_isolated():
            out = serialize(
                ScatterChart(SAMPLE, y_unit="ms", x_unit="s").render()
            )
        # Both units appear in the display payloads.
        assert "ms" in out
        assert "s)" in out  # x unit lands on the x side of the pair

    def test_no_bindable_props(self) -> None:
        assert ScatterChart.BINDABLE_PROPS == ()
