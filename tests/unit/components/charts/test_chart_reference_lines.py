"""The charts' reference lines: ``y_reference_lines`` at a value,
``x_reference_lines`` at a moment.

Asked by Radar (2026-11-07): a company's price with each buy and each
sale marked WHERE it happened. ``reference_lines`` only drew horizontal
lines at values; a buy price and a sale price two weeks apart, a few
cents from each other, put their labels on top of one another and said
nothing of when. The horizontal kind took the axis' prefix the same day
(``y_reference_lines``, like ``y_min`` / ``y_unit``), and a bad item —
a bare string, walked letter by letter — stopped dropping out in silence.
"""

from __future__ import annotations

import re
from datetime import date, timedelta

import pytest

from bretzel.components.base.attrs import ComponentUsageError
from bretzel.components.base.testing import render_isolated
from bretzel.components.charts.bar_chart.bar_chart import BarChart
from bretzel.components.charts.line_chart.line_chart import LineChart
from bretzel.components.charts.reference import Reference
from bretzel.components.charts.scatter_chart.scatter_chart import ScatterChart
from bretzel.core.serialize import serialize

DAYS = [date(2026, 10, 1) + timedelta(days=i) for i in range(20)]
PRICES = [(day, 48 + i * 0.5) for i, day in enumerate(DAYS)]


def _render(data=PRICES, **kwargs) -> str:
    with render_isolated():
        return serialize(LineChart(data, **kwargs).render())


def _group(html: str, name: str) -> str:
    match = re.search(rf'<g class="{name}">(.*?)</g>', html, re.S)
    assert match, f"no {name} group rendered"
    return match.group(1)


def _vertical_xs(html: str) -> list[str]:
    lines = re.findall(r'<line [^>]*x1="([^"]+)"[^>]*x2="([^"]+)"',
                       _group(html, "bz-line-x-refs"))
    assert all(x1 == x2 for x1, x2 in lines), "a mark's line is not vertical"
    return [x1 for x1, _ in lines]


def test_a_mark_at_a_date_draws_a_vertical_line_and_its_label() -> None:
    html = _render(x_reference_lines=[(DAYS[5], "achat"), (DAYS[15], "vente", "error")])
    assert len(_vertical_xs(html)) == 2
    labels = _group(html, "bz-line-x-ref-labels")
    assert "achat" in labels and "vente" in labels


def test_the_line_sits_where_its_moment_is() -> None:
    # Day 0 to day 19: day 5 is at 5/19 of the plot, whatever the padding.
    first, last = _vertical_xs(_render(x_reference_lines=[(DAYS[0], "a"),
                                                          (DAYS[19], "b")]))
    assert float(first.rstrip("%")) == pytest.approx(0, abs=0.01)
    assert float(last.rstrip("%")) == pytest.approx(100, abs=0.01)


def test_a_mark_past_the_data_widens_the_axis() -> None:
    later = DAYS[-1] + timedelta(days=10)
    xs = _vertical_xs(_render(x_reference_lines=[(later, "plus tard")]))
    assert float(xs[0].rstrip("%")) == pytest.approx(100, abs=0.01)


def test_a_reference_object_and_a_number_are_accepted() -> None:
    html = _render([(0, 3), (1, 9), (2, 4)],
                   x_reference_lines=[Reference(value=1, label="sortie", color="primary")])
    assert len(_vertical_xs(html)) == 1
    assert "sortie" in _group(html, "bz-line-x-ref-labels")


def test_a_mark_without_a_label_says_its_moment() -> None:
    labels = _group(_render(x_reference_lines=[(DAYS[5],)]), "bz-line-x-ref-labels")
    assert re.search(r">[^<]+</text>", labels), "an unnamed mark wrote nothing"


def test_two_close_marks_put_their_labels_on_two_rows() -> None:
    labels = _group(_render(x_reference_lines=[(DAYS[8], "vente"), (DAYS[9], "rachat")]),
                    "bz-line-x-ref-labels")
    ys = re.findall(r'<text [^>]*y="([^"]+)"', labels)
    assert len(set(ys)) == 2, f"two close labels share a row: {ys}"


def test_a_mark_that_is_not_a_moment_is_refused() -> None:
    with pytest.raises(ComponentUsageError, match="x_reference_lines"):
        _render(x_reference_lines=["achat"])
    with pytest.raises(ComponentUsageError, match="x_reference_lines"):
        _render(x_reference_lines=[("lundi", "achat")])


def test_no_mark_draws_no_group() -> None:
    assert "bz-line-x-refs" not in _render()


# ── y_reference_lines, on the three charts ─────────────────────────


@pytest.mark.parametrize("cls, data", [
    (LineChart, [(0, 3), (1, 9), (2, 4)]),
    (ScatterChart, [(0, 3), (1, 9), (2, 4)]),
    (BarChart, [("a", 3), ("b", 9)]),
], ids=["line", "scatter", "bar"])
def test_y_reference_lines_draw_and_refuse_what_is_not_a_value(cls, data) -> None:
    with render_isolated():
        html = serialize(cls(data, y_reference_lines=[(5, "Objectif")]).render())
    assert "Objectif" in html
    for bad in ("Objectif", [("cinq", "Objectif")], ["Objectif"]):
        with render_isolated(), pytest.raises(ComponentUsageError,
                                              match="y_reference_lines"):
            cls(data, y_reference_lines=bad)


def test_the_scatter_chart_marks_a_moment_too() -> None:
    with render_isolated():
        html = serialize(ScatterChart([(0, 3), (1, 9), (2, 4)],
                                      x_reference_lines=[(1, "changement")]).render())
    assert len(_vertical_xs(html)) == 1
    assert "changement" in _group(html, "bz-line-x-ref-labels")


@pytest.mark.parametrize("cls, data", [
    (LineChart, [(0, 3), (1, 9), (2, 4)]),
    (ScatterChart, [(0, 3), (1, 9), (2, 4)]),
    (BarChart, [("a", 3), ("b", 9)]),
], ids=["line", "scatter", "bar"])
def test_a_bare_value_is_a_line_without_a_label(cls, data) -> None:
    """``y_reference_lines=[4]``: nothing to guess, so nothing to refuse
    (refused until the Portail's load chart, 2026-11-07)."""
    with render_isolated():
        bare = serialize(cls(data, y_reference_lines=[5]).render())
    with render_isolated():
        tupled = serialize(cls(data, y_reference_lines=[(5, "")]).render())
    assert bare == tupled


def test_a_bare_moment_is_a_mark_that_says_it() -> None:
    assert _render(x_reference_lines=[1]) == _render(x_reference_lines=[(1, None)])
