"""The base every chart shares (2026-10-29): what one had and its
neighbour did not, made common.

- ``y_min`` / ``y_max`` (and ``x_min`` / ``x_max``): the axis covers them
  at least, a value past them still shows;
- ``x_label`` / ``y_label``: the axis titles, level;
- ``on_item_click`` on the line (one series) and the scatter;
- the legend hides a series of grouped bars — not a stack;
- the table behind the drawing: ``sr-only`` always, ``show_data`` shows it;
- the keyboard: a chart with points is one tab stop.

What a browser must do with them (the arrows, Enter, the legend) is
``tests/probes/probe_charts.py``.
"""

from __future__ import annotations

import re
from datetime import date

import pytest

from bretzel.components.base.attrs import ComponentUsageError
from bretzel.components.base.testing import render_isolated
from bretzel.components.charts.bar_chart.bar_chart import BarChart
from bretzel.components.charts.line_chart.line_chart import LineChart
from bretzel.components.charts.pie_chart.pie_chart import PieChart
from bretzel.components.charts.scatter_chart.scatter_chart import ScatterChart
from bretzel.components.charts.series import Series, with_series
from bretzel.components.charts.sparkline.sparkline import Sparkline
from bretzel.core.serialize import serialize


def picked(x, y) -> None:
    """A module-level handler: lambdas are refused."""


def html(build, data, **props) -> str:
    with render_isolated():
        return serialize(build(data, **props).render())


def ticks(out: str) -> set[str]:
    return set(re.findall(r">(\d+)<", out))


GROUPED = [Series(name="A", data=[("x", 1), ("y", 2)]),
           Series(name="B", data=[("x", 3), ("y", 1)])]


class TestBounds:
    def test_y_max_ends_the_axis(self) -> None:
        assert "20" in ticks(html(BarChart, [("a", 13.2), ("b", 12.6)], y_max=20))
        assert "20" not in ticks(html(BarChart, [("a", 13.2), ("b", 12.6)]))

    def test_a_value_past_the_bound_stays_seen(self) -> None:
        assert "30" in ticks(html(BarChart, [("a", 21)], y_max=20))

    def test_a_20_on_20_ends_at_20_not_a_padded_25(self) -> None:
        assert "25" not in ticks(html(BarChart, [("a", 20)], y_max=20))

    def test_line_and_scatter_take_both_axes(self) -> None:
        out = html(LineChart, [(1, 3), (2, 5)], y_max=20, x_min=0, x_max=10)
        assert {"20", "10"} <= ticks(out)
        out = html(ScatterChart, [(1, 3), (2, 5)], y_min=0, y_max=20, x_max=10)
        assert {"20", "10"} <= ticks(out)

    def test_dates_as_x_bounds(self) -> None:
        html(LineChart, [(date(2026, 9, 7), 3)], x_min=date(2026, 9, 1),
             x_max=date(2026, 9, 30))

    def test_a_bar_axis_cannot_start_above_zero(self) -> None:
        with pytest.raises(ComponentUsageError, match="grows from 0"):
            html(BarChart, [("a", 1)], y_min=5)

    def test_no_bound_on_a_100_percent_stack(self) -> None:
        with pytest.raises(ComponentUsageError, match="stacked_100"):
            html(BarChart, GROUPED, variant="stacked_100", y_max=50)


class TestAxisTitles:
    @pytest.mark.parametrize("build, data", [
        (BarChart, [("a", 1)]), (LineChart, [(1, 2)]), (ScatterChart, [(1, 2)]),
    ])
    def test_the_titles_are_written(self, build, data) -> None:
        out = html(build, data, x_label="note", y_label="élèves")
        assert ">élèves</div>" in out and ">note</div>" in out

    def test_lying_bars_put_the_value_axis_below(self) -> None:
        out = html(BarChart, [("a", 1)], orientation="horizontal",
                   x_label="matière", y_label="moyenne")
        assert out.index(">matière</div>") < out.index(">moyenne</div>")


class TestClick:
    def test_a_line_point_is_clickable(self) -> None:
        assert html(LineChart, [(1, 2), (2, 3)], on_item_click=picked).count("hx-post") == 2

    def test_a_scatter_point_is_clickable(self) -> None:
        assert html(ScatterChart, [(1, 2), (2, 3)], on_item_click=picked).count("hx-post") == 2

    def test_several_lines_cannot_say_which_point(self) -> None:
        with pytest.raises(ComponentUsageError, match="several series"):
            html(LineChart, [Series(name="a", data=[(1, 2)]),
                             Series(name="b", data=[(1, 3)])], on_item_click=picked)


class TestAClickSaysItsSeries:
    """A bar or a point belongs to one series; the column of a line does not."""

    TWO = [Series(name="5A", data=[("T1", 2)]), Series(name="5B", data=[("T1", 3)])]
    POINTS = [Series(name="5A", data=[(1, 2)]), Series(name="5B", data=[(1, 3)])]

    @pytest.mark.parametrize("options", [
        {}, {"variant": "stacked"}, {"variant": "stacked_100"}, {"orientation": "horizontal"},
        {"variant": "stacked", "orientation": "horizontal"}, {"variant": "stacked_100", "orientation": "horizontal"},
    ])
    def test_bars_name_their_series(self, options) -> None:
        out = html(BarChart, self.TWO, on_item_click="go($event.detail)", **options)
        assert "5A" in out and "series" in out

    def test_points_name_their_series(self) -> None:
        assert "series" in html(ScatterChart, self.POINTS, on_item_click="go($event.detail)")

    def test_one_series_keeps_two_arguments(self) -> None:
        out = html(BarChart, [("T1", 2)], on_item_click="go($event.detail)")
        assert "series" not in out.split("bz-on:item_click", 1)[-1].split(">", 1)[0]

    def test_with_series_only_adds_it_when_there_are_several(self) -> None:
        one, two = [Series(name="a")], [Series(name="a"), Series(name="b")]
        assert with_series({"x": 1}, one[0], one) == {"x": 1}
        assert with_series({"x": 1}, two[1], two) == {"x": 1, "series": "b"}


class TestLegend:
    def test_grouped_bars_hide_a_series(self) -> None:
        out = html(BarChart, GROUPED)
        assert "barScope" in out and "aria-pressed" in out
        assert out.count('bz-show="isVisible(') == 4

    def test_a_stack_keeps_its_legend_still(self) -> None:
        out = html(BarChart, GROUPED, variant="stacked")
        assert "barScope" not in out and "aria-pressed" not in out


class TestDataTable:
    @pytest.mark.parametrize("build, data", [
        (BarChart, [("a", 1), ("b", 2)]), (LineChart, [(1, 2), (2, 3)]),
        (ScatterChart, [(1, 2), (2, 3)]), (PieChart, [("a", 1), ("b", 3)]),
    ])
    def test_always_there_for_a_screen_reader(self, build, data) -> None:
        out = html(build, data)
        # On a div: a <table> ignores the 1 px of ``sr-only``.
        assert '<div class="sr-only"><table>' in out and "<details" not in out

    @pytest.mark.parametrize("build, data", [
        (BarChart, [("a", 1), ("b", 2)]), (LineChart, [(1, 2), (2, 3)]),
        (ScatterChart, [(1, 2), (2, 3)]), (PieChart, [("a", 1), ("b", 3)]),
    ])
    def test_show_data_unfolds_it(self, build, data) -> None:
        out = html(build, data, show_data=True)
        assert "<details" in out and "Show the data" in out and "sr-only" not in out

    def test_the_pie_says_each_share(self) -> None:
        assert "75%" in html(PieChart, [("a", 1), ("b", 3)])


class TestKeyboard:
    @pytest.mark.parametrize("build, data", [
        (BarChart, [("a", 1)]), (LineChart, [(1, 2)]),
        (ScatterChart, [(1, 2)]), (PieChart, [("a", 1)]),
    ])
    def test_a_chart_with_points_is_one_tab_stop(self, build, data) -> None:
        out = html(build, data)
        assert out.count('tabindex="0"') == 1 and 'bz-on:keydown="key($event)"' in out

    def test_an_empty_chart_is_not_a_tab_stop(self) -> None:
        assert 'tabindex="0"' not in html(BarChart, [])

    def test_the_sparkline_stays_as_it_was(self) -> None:
        assert 'tabindex' not in html(Sparkline, [1, 2, 3])
