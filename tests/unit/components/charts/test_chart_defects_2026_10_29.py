"""What the charts got wrong, found on a spread of marks.

- a « 0 » written over every empty bar;
- « 0.5 » on an axis of counts, on lines and clouds as on bars;
- a point that is not one, skipped without a word — a list of dicts
  drew « No data » on every histogram.
"""

from __future__ import annotations

import pytest

from bretzel.components.base.attrs import ComponentUsageError
from bretzel.components.base.testing import render_isolated
from bretzel.components.charts.bar_chart.bar_chart import BarChart
from bretzel.components.charts.line_chart.line_chart import LineChart
from bretzel.components.charts.pie_chart.pie_chart import PieChart
from bretzel.components.charts.scatter_chart.scatter_chart import ScatterChart
from bretzel.components.charts.series import Series
from bretzel.components.charts.sparkline.sparkline import Sparkline
from bretzel.core.serialize import serialize


def html(build, data, **props) -> str:
    with render_isolated():
        return serialize(build(data, **props).render())


class TestNoZeroLabel:
    @pytest.mark.parametrize("orientation", ["vertical", "horizontal"])
    def test_an_empty_bar_carries_no_label(self, orientation: str) -> None:
        # The empty bar adds its category's name, and no « 0 » above it.
        with_zero = html(BarChart, [("a", 0), ("b", 3)], show_values=True,
                         orientation=orientation)
        without = html(BarChart, [("b", 3)], show_values=True, orientation=orientation)
        assert with_zero.count("<text") - without.count("<text") == 1


class TestWholeTicks:
    def test_a_line_of_counts(self) -> None:
        assert ">0.5<" not in html(LineChart, [(0, 0), (1, 1), (2, 1)])
        assert ">0.5<" in html(LineChart, [(0, 0.2), (1, 1), (2, 1.2)])

    def test_a_cloud_of_counts(self) -> None:
        assert ">0.5<" not in html(ScatterChart, [(0, 0), (1, 1)])
        assert ">0.5<" in html(ScatterChart, [(0, 0.2), (1, 1.2)])


@pytest.mark.parametrize("build, data", [
    (BarChart, [{"label": "a", "value": 1}]),
    (BarChart, [("a", None)]),
    (BarChart, [Series(name="s", data=[1, 2])]),
    (PieChart, [("a", "b")]),
    (LineChart, [1, "x"]),
    # A None y is a HOLE on a line since 2026-11-07 (test_line_chart_gaps):
    # what is not a point there is a y that is not a number.
    (LineChart, [Series(name="s", data=[(0, "x")])]),
    (ScatterChart, [(1, 2, 3)]),
    (Sparkline, [1, "x"]),  # None is a hole there too since 2026-11-07
])
def test_a_point_that_is_not_one_is_said(build, data) -> None:
    with pytest.raises(ComponentUsageError, match="is not a point of data="):
        html(build, data)
