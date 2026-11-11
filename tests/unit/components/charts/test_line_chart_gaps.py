"""``ui.line_chart`` draws holes, and series on their own x values.

Asked by Radar (2026-11-07): a European stock and the Nasdaq-100 do
not close on the same days. Until then every series had to carry the
same x values in the same order (« must share the same x values »), and
a ``None`` y was refused: the app re-aligned the dates by hand and
invented a value for each holiday.

- a ``None`` y is a HOLE: the curve stops and starts again, never drawn
  at zero, never bridged; a point alone between two holes is a dot;
- each series keeps its own x; the hover, the tooltip and the hidden
  table read every series on the union of the x values, « — » where a
  series has no point.
"""

from __future__ import annotations

import re
from datetime import date, timedelta

from bretzel.components.base.testing import render_isolated
from bretzel.components.charts.line_chart.line_chart import LineChart
from bretzel.components.charts.series import Series
from bretzel.core.serialize import serialize


def _render(data, **kwargs) -> str:
    with render_isolated():
        return serialize(LineChart(data, **kwargs).render())


def _line_d(html: str) -> list[str]:
    """The ``d`` of each series' line path."""
    return re.findall(r'<path class="[^"]*"[^>]*d="([^"]*)"[^>]*stroke-width', html)


def test_a_hole_breaks_the_line_in_two() -> None:
    (d,) = _line_d(_render([(0, 1), (1, 2), (2, None), (3, 4), (4, 5)], smooth=False))
    assert d.count("M") == 2, f"the hole was bridged: {d}"


def test_a_hole_is_not_a_zero() -> None:
    html = _render([(0, 10), (1, 12), (2, None), (3, 11)], smooth=False)
    axis = re.search(r'<g class="bz-line-axes">(.*?)</g>', html, re.S)
    assert axis, "no y axis rendered"
    ticks = [float(t.replace(",", ".")) for t in re.findall(r">(-?\d+(?:[.,]\d+)?)</text>",
                                                             axis.group(1))]
    assert min(ticks) > 5, f"the axis went down to zero for a hole: {ticks}"


def test_a_point_alone_between_two_holes_is_a_dot() -> None:
    html = _render([(0, 1), (1, None), (2, 3), (3, None), (4, 5), (5, 6)], smooth=False)
    (d,) = _line_d(html)
    assert d.count("M") == 1, "only the last stretch has two points"
    assert html.count('class="') and len(re.findall(r"<circle [^>]*r=\"\d", html)) >= 2


def test_a_bare_list_takes_holes_too() -> None:
    (d,) = _line_d(_render([1, 2, None, 4, 5], smooth=False))
    assert d.count("M") == 2


def test_the_area_stops_at_the_hole_too() -> None:
    html = _render([(0, 1), (1, 2), (2, None), (3, 4), (4, 5)], area_fill=True,
                   smooth=False)
    area = re.search(r'fill="url\(#[^"]+\)"[^>]*d="([^"]*)"', html)
    assert area and area.group(1).count("Z") == 2


DAYS = [date(2026, 11, 2) + timedelta(days=i) for i in range(5)]


def _two_markets() -> list[Series]:
    # The stock has no close on day 2 (a holiday at home), the index
    # none on day 4.
    return [
        Series(name="Action", data=[(d, 10 + i) for i, d in enumerate(DAYS) if i != 2]),
        Series(name="Indice", data=[(d, 20 + i) for i, d in enumerate(DAYS) if i != 4]),
    ]


def test_series_on_different_days_draw_together() -> None:
    html = _render(_two_markets(), smooth=False)
    lines = _line_d(html)
    assert len(lines) == 2
    # A missing day is not a hole: each line stays in one piece.
    assert all(d.count("M") == 1 for d in lines)


def test_the_hover_reads_the_union_of_the_days() -> None:
    html = _render(_two_markets(), smooth=False)
    displays = re.findall(r'<rect [^>]*data-bz-display="([^"]*)"', html)
    assert len(displays) == 5, f"{len(displays)} columns for 5 days"
    # A date axis writes its display as a client expression, the dash
    # escaped in it: « Action: — ».
    def says_dash(display: str, name: str) -> bool:
        return f"{name}: —" in display or f"{name}: \\u2014" in display

    assert says_dash(displays[2], "Action") and says_dash(displays[4], "Indice"), displays
    # The active dot of a series that has no point in a column stays hidden.
    assert "null" in html and "!== null" in html


def test_a_series_without_a_point_says_a_dash() -> None:
    html = _render(_two_markets(), smooth=False, show_data=True)
    cells = re.findall(r"<td[^>]*>([^<]*)</td>", html)
    assert cells.count("—") == 2, cells


def picked(x, y) -> None:  # pragma: no cover - never called here
    """A handler for the click test: it only has to be addressable."""


def test_a_click_is_only_on_a_point() -> None:
    with render_isolated():
        html = serialize(LineChart([(0, 1), (1, None), (2, 3)],
                                   on_item_click=picked).render())
    assert html.count("hx-post") == 2


# ── ui.sparkline reads a None the same way (R1) ─────────────────────


def _spark(data, **kwargs) -> str:
    from bretzel.components.charts.sparkline.sparkline import Sparkline

    with render_isolated():
        return serialize(Sparkline(data, **kwargs).render())


def _spark_line_d(html: str) -> str:
    match = re.search(r'<path [^>]*d="([^"]*)"[^>]*stroke-width', html)
    assert match, "no line path"
    return match.group(1)


def test_a_sparkline_stops_at_a_hole_too() -> None:
    d = _spark_line_d(_spark([1, 2, None, 4, 5]))
    assert d.count("M") == 2, f"the hole was bridged: {d}"


def test_a_sparkline_point_alone_is_a_dot() -> None:
    html = _spark([1, None, 3, None, 5, 6])
    assert html.count("<circle") == 2


def test_a_sparkline_ending_on_a_hole_draws_no_last_dot() -> None:
    assert "<circle" not in _spark([1, 2, 3, None], show_last_dot=True)
    assert _spark([1, 2, 3], show_last_dot=True).count("<circle") == 1


def test_a_sparkline_of_holes_only_draws_nothing() -> None:
    assert "<path" not in _spark([None, None])
