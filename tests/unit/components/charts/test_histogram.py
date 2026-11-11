"""``ui.histogram`` — raw values counted per tranche (2026-10-29).

The tranches are the point: four apps counted marks by hand and each had
its bounds a little wrong. What a browser does with the bars (keyboard,
legend, table) is the bar chart's, tested there.
"""

from __future__ import annotations

import pytest

from bretzel.components.base.attrs import ComponentUsageError
from bretzel.components.base.testing import render_isolated
from bretzel.components.charts.histogram.histogram import Histogram, tranches
from bretzel.core.serialize import serialize


def picked(low, high) -> None:
    """A module-level handler: lambdas are refused."""


def html(data, **props) -> str:
    with render_isolated():
        return serialize(Histogram(data, **props).render())


def labels(**kw) -> list[str]:
    return [label for _low, _high, label in tranches(**kw)]


class TestTranches:
    def test_a_step_of_one_counts_per_point_the_top_included(self) -> None:
        got = labels(values=[20.0], x_min=0, x_max=20, step=None, bins=None)
        assert got == [str(n) for n in range(21)]

    def test_a_wider_step_holds_the_top_in_its_last_tranche(self) -> None:
        got = labels(values=[20.0], x_min=0, x_max=20, step=5, bins=None)
        assert got == ["0–5", "5–10", "10–15", "15–20"]

    def test_past_forty_about_ten_tranches(self) -> None:
        got = labels(values=[60.0], x_min=0, x_max=60, step=None, bins=None)
        assert got[0] == "0–6" and got[-1] == "54–60" and len(got) == 10

    def test_x_max_is_a_minimum_a_bonus_adds_a_tranche(self) -> None:
        assert labels(values=[21.0], x_min=0, x_max=20, step=None, bins=None)[-1] == "21"

    def test_irregular_bins(self) -> None:
        got = labels(values=[8.0], x_min=None, x_max=None, step=None, bins=[0, 9, 13, 15, 20])
        assert got == ["0–9", "9–13", "13–15", "15–20"]


class TestCounts:
    def test_each_mark_in_its_tranche(self) -> None:
        # Read in the table behind the drawing: « 12 » holds 12 and 12,5.
        out = html([12, 12.5, 20, 0], x_min=0, x_max=20)
        assert "<td>12</td><td>2</td>" in out and "<td>20</td><td>1</td>" in out
        assert "<td>0</td><td>1</td>" in out and "<td>13</td><td>0</td>" in out

    def test_twenty_on_twenty_is_counted_in_bins(self) -> None:
        out = html([20, 15], bins=[0, 10, 20], show_values=True)
        assert ">2<" in out


class TestRefused:
    def test_bins_and_step_together(self) -> None:
        with pytest.raises(ComponentUsageError, match="bins= gives every bound"):
            html([1], bins=[0, 10], step=2)

    def test_a_value_outside_the_bins(self) -> None:
        with pytest.raises(ComponentUsageError, match="outside bins"):
            html([25], bins=[0, 10, 20])

    def test_bins_not_rising(self) -> None:
        with pytest.raises(ComponentUsageError, match="each above"):
            html([1], bins=[0, 10, 5])

    def test_a_value_that_is_not_a_number(self) -> None:
        with pytest.raises(ComponentUsageError, match="is not a point of data="):
            html([12, None])


class TestMean:
    def test_the_mean_is_marked_and_said(self) -> None:
        out = html([10, 14], x_min=0, x_max=20, show_mean=True)
        assert "bz-bar-mark" in out and "Mean 12" in out

    def test_no_mean_unless_asked(self) -> None:
        assert "bz-bar-mark" not in html([10, 14], x_min=0, x_max=20)


class TestClick:
    def test_the_click_says_the_tranche(self) -> None:
        with render_isolated():
            chart = Histogram([12], x_min=0, x_max=20, step=5, on_item_click=picked)
        assert chart._item_payload("10–15", 1) == {"low": 10, "high": 15}


def test_empty_says_it_is_a_histogram() -> None:
    assert "Histogram" in html([], empty_text="No mark yet")
