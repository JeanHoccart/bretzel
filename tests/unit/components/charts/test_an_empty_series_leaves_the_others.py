"""A chart is empty when no series has a point, and dated when one has a date.

The two questions were asked of the first sample of the first series: an
empty first series emptied the whole line chart, and took a date axis for a
numeric one.
"""

from __future__ import annotations

from datetime import date, datetime

import pytest

from bretzel.components.base.testing import render_isolated
from bretzel.components.charts.line_chart.line_chart import LineChart
from bretzel.components.charts.scatter_chart.scatter_chart import ScatterChart
from bretzel.components.charts.series import Series, first_x, has_points, is_date_axis, x_back
from bretzel.core.serialize import serialize

DAYS = [(date(2026, 1, 5), 1.0), (date(2026, 3, 9), 2.0)]
EMPTY_THEN_DATES = [Series("none", []), Series("sales", DAYS)]


def _html(build: type, data: list, **props: object) -> str:
    with render_isolated():
        return serialize(build(data, **props).render())


@pytest.mark.parametrize("build", [LineChart, ScatterChart])
def test_an_empty_first_series_does_not_empty_the_chart(build: type) -> None:
    html = _html(build, EMPTY_THEN_DATES)
    assert "<svg" in html
    assert "No data" not in html


@pytest.mark.parametrize("build", [LineChart, ScatterChart])
def test_a_chart_with_no_point_at_all_is_empty(build: type) -> None:
    assert "No data" in _html(build, [Series("a", []), Series("b", [])])


def test_the_date_axis_is_read_on_every_series() -> None:
    assert is_date_axis(EMPTY_THEN_DATES)
    assert not is_date_axis([Series("none", []), Series("n", [(1, 2)])])
    # Labelled as dates, not as the timestamps they are drawn on.
    assert ">Jan 05</text>" in _html(LineChart, EMPTY_THEN_DATES)


def test_x_back_gives_a_date_back_from_any_series() -> None:
    assert x_back(EMPTY_THEN_DATES)(datetime(2026, 1, 5).timestamp()) == "2026-01-05"
    assert first_x([Series("none", []), Series("n", [(7, 2)])]) == 7
    assert x_back([3.0, 4.0])(1.0) == 1


def test_has_points() -> None:
    assert not has_points([])
    assert not has_points([Series("a", [])])
    assert has_points([Series("a", []), Series("b", [(1, 2)])])
