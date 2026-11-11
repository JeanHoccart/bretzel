"""The series charts' frame: width, margins, depth and colours.

Four defects measured in Chromium while writing the showcase
(2026-09-29), each invisible to the smoke tests next door:

- a chart kept a fixed internal width of 600 px — a bar chart drew
  518 px centred in a 938-px card, a line chart stayed 600 px on the
  left of it;
- a reference line's label was drawn BEFORE the bars, so under them;
- a long ``y_unit`` started left of the chart and was cut by the card;
- two series came out the same green under a green identity, the
  automatic cycle going primary → success.
"""

from __future__ import annotations

import re

import pytest

from bretzel.components.base.testing import render_isolated
from bretzel.components.charts.bar_chart.bar_chart import BarChart
from bretzel.components.charts.line_chart.line_chart import LineChart
from bretzel.components.charts.reference import Reference
from bretzel.components.charts.scatter_chart.scatter_chart import ScatterChart
from bretzel.components.charts.series import Series
from bretzel.core.serialize import serialize

CHARTS = [BarChart, LineChart, ScatterChart]

_BARS = [("Mon", 12), ("Tue", 19), ("Wed", 8)]
_POINTS = [(0, 3), (1, 9), (2, 4), (3, 12)]


def _data(cls: type) -> list:
    return _BARS if cls is BarChart else _POINTS


def _render(cls: type, data: list | None = None, **kwargs) -> str:
    with render_isolated():
        return serialize(cls(data if data is not None else _data(cls),
                             **kwargs).render())


def _svg_tag(html: str) -> str:
    match = re.search(r"<svg[^>]*>", html)
    assert match, "no <svg> rendered"
    return match.group(0)


def _margin_left(html: str) -> int:
    match = re.search(r"margin-left:(\d+)px", _svg_tag(html))
    assert match, f"the plot declares no left margin: {_svg_tag(html)}"
    return int(match.group(1))


# ── 1. The chart fills its container ─────────────────────────────────


@pytest.mark.parametrize("cls", CHARTS, ids=lambda c: c.__name__)
def test_by_default_the_plot_spans_its_container(cls: type) -> None:
    """No ``viewBox`` (it fixes the aspect ratio, so a wide card
    letterboxes the drawing), and a width that is the container's less
    the margins."""
    svg = _svg_tag(_render(cls))
    assert "viewBox" not in svg
    assert re.search(r'style="width:calc\(100% - \d+px\)', svg), svg


@pytest.mark.parametrize("cls", CHARTS, ids=lambda c: c.__name__)
def test_every_hover_target_is_placed_in_shares_of_the_plot(cls: type) -> None:
    """A pixel x could only be right for ONE width. The hover targets —
    a bar's hit column, a line's column, a scatter dot — are the
    marks a user points at, so they are the ones that must follow."""
    html = _render(cls)
    xs = re.findall(r'<(?:rect|circle)\b[^>]*? (?:x|cx)="([^"]+)"', html)
    assert xs, "no positioned mark found"
    assert all(x.endswith("%") for x in xs), xs


@pytest.mark.parametrize("cls", CHARTS, ids=lambda c: c.__name__)
def test_an_explicit_width_is_pixels_capped_by_the_container(cls: type) -> None:
    root = re.search(r"<div[^>]*>", _render(cls, width=400)).group(0)
    assert "width:400px;max-width:100%" in root


@pytest.mark.parametrize("cls", CHARTS, ids=lambda c: c.__name__)
def test_the_author_style_still_wins_over_the_width(cls: type) -> None:
    root = re.search(r"<div[^>]*>", _render(
        cls, width=400, style="width:250px")).group(0)
    assert root.index("width:400px") < root.index("width:250px")


def test_a_horizontal_bar_chart_is_placed_in_shares_too() -> None:
    html = _render(BarChart, orientation="horizontal")
    widths = re.findall(r'<rect\b[^>]*? width="([^"]+)"', html)
    assert widths and all(w.endswith("%") for w in widths), widths


# ── 2. A reference label is painted over the data ────────────────────


def _last_data_mark(cls: type, html: str) -> int:
    marker = {BarChart: "bz-bar-fill", LineChart: "<path",
              ScatterChart: "<circle"}[cls]
    return html.rindex(marker)


@pytest.mark.parametrize("cls", CHARTS, ids=lambda c: c.__name__)
def test_a_reference_label_is_painted_after_the_data(cls: type) -> None:
    html = _render(cls, y_reference_lines=[Reference(value=5, label="Goal")])
    assert html.index(">Goal") > _last_data_mark(cls, html)


@pytest.mark.parametrize("cls", CHARTS, ids=lambda c: c.__name__)
def test_the_reference_line_itself_stays_behind(cls: type) -> None:
    html = _render(cls, y_reference_lines=[Reference(value=5, label="Goal")])
    first_line = html.index('stroke-dasharray="4 4"')
    first_mark = html.index({BarChart: "bz-bar-fill", LineChart: "<path",
                             ScatterChart: "<circle"}[cls])
    assert first_line < first_mark


def test_a_horizontal_bar_reference_label_is_painted_after_the_bars() -> None:
    html = _render(BarChart, orientation="horizontal",
                   y_reference_lines=[Reference(value=5, label="Goal")])
    assert html.index(">Goal") > html.rindex("bz-bar-fill")


# ── 3. The left margin holds the widest label ────────────────────────

#: A lower bound of a glyph's advance, in ems, for any sans font. The
#: margin must hold AT LEAST that — the estimate itself may be larger.
_MIN_GLYPH_EM = 0.5
_AXIS_FONT_MD = 12


def _y_labels(html: str) -> list[str]:
    return re.findall(r'<text[^>]*? x="-6"[^>]*>([^<]+)</text>', html)


@pytest.mark.parametrize("cls", CHARTS, ids=lambda c: c.__name__)
def test_the_left_margin_holds_a_long_unit(cls: type) -> None:
    html = _render(cls, y_unit="requests/s")
    widest = max(_y_labels(html), key=len)
    assert "requests/s" in widest
    assert _margin_left(html) >= len(widest) * _AXIS_FONT_MD * _MIN_GLYPH_EM + 6


@pytest.mark.parametrize("cls", CHARTS, ids=lambda c: c.__name__)
def test_short_labels_keep_the_historical_margin(cls: type) -> None:
    """A chart that fitted does not move."""
    assert _margin_left(_render(cls)) == 48


def test_a_horizontal_bar_margin_holds_a_long_category() -> None:
    html = _render(BarChart, [("Customer acquisition cost", 3), ("Churn", 5)],
                   orientation="horizontal")
    assert _margin_left(html) >= (
        len("Customer acquisition cost") * _AXIS_FONT_MD * _MIN_GLYPH_EM + 6
    )


# ── 4. Two series, two colours ───────────────────────────────────────


def test_two_bar_series_take_the_brand_pair() -> None:
    html = _render(BarChart, [
        Series(name="A", data=[("Q1", 5), ("Q2", 8)]),
        Series(name="B", data=[("Q1", 7), ("Q2", 3)]),
    ])
    assert "bz-c-primary" in html and "bz-c-secondary" in html
    assert "bz-c-success" not in html


@pytest.mark.parametrize("cls", [LineChart, ScatterChart],
                         ids=lambda c: c.__name__)
def test_two_xy_series_take_the_brand_pair(cls: type) -> None:
    html = _render(cls, [
        Series(name="A", data=[(0, 1), (1, 2)]),
        Series(name="B", data=[(0, 2), (1, 3)]),
    ])
    assert "bz-c-primary" in html and "bz-c-secondary" in html
    assert "bz-c-success" not in html
