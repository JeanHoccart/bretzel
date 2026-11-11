"""A smoothed line never draws a value the data does not have.

``smooth=True`` is the default of ``ui.line_chart`` (and an option of
``ui.sparkline`` and the area fills). Its Catmull-Rom curve dipped under
a flat stretch and rose above the highest close as soon as the x steps
were uneven — a week-end in a series of daily prices. Measured on Radar
(2026-11-07): control points at 8.3 and 21.7 for data between 10 and 20.
A monotone cubic (D3's ``curveMonotoneX``) keeps every segment inside
the interval of its two points.
"""

from __future__ import annotations

import random
import re

import pytest

from bretzel.components.charts._svg import area_path, smooth_path


def _segments(d: str) -> list[tuple[tuple[float, float], list[tuple[float, float]]]]:
    """Each cubic segment: its start, then its two control points and its end."""
    start = re.match(r"M(-?[\d.]+),(-?[\d.]+)", d)
    assert start, d
    here = (float(start.group(1)), float(start.group(2)))
    out = []
    for c in re.findall(r"C([^CLZ]+)", d):
        nums = [float(v) for v in re.findall(r"-?[\d.]+", c)]
        pts = [(nums[0], nums[1]), (nums[2], nums[3]), (nums[4], nums[5])]
        out.append((here, pts))
        here = pts[-1]
    return out


def _assert_inside(points: list[tuple[float, float]]) -> None:
    d = smooth_path(points)
    for start, (c1, c2, end) in _segments(d):
        low, high = min(start[1], end[1]), max(start[1], end[1])
        for c in (c1, c2):
            assert low - 1e-6 <= c[1] <= high + 1e-6, (
                f"a control point at y={c[1]} leaves [{low}, {high}] between "
                f"{start} and {end}: the curve draws a value the data never had")


SERIES = {
    "a week-end then a jump": [(0, 10), (1, 10), (2, 10), (5, 20), (6, 20), (7, 20)],
    "a peak": [(0, 0), (5, 5), (10, 0)],
    "a plateau between two moves": [(0, 1), (1, 4), (2, 4), (3, 4), (4, 9)],
    "uneven steps": [(0, 3), (0.5, 9), (4, 4), (4.2, 12), (9, 1)],
}


@pytest.mark.parametrize("points", SERIES.values(), ids=SERIES.keys())
def test_a_smoothed_segment_stays_between_its_two_points(points) -> None:
    _assert_inside(points)


def test_random_daily_closes_never_overshoot() -> None:
    rng = random.Random(7)
    for _ in range(50):
        x, points = 0.0, []
        for _ in range(30):
            x += rng.choice((1, 1, 1, 1, 3))  # week-ends
            points.append((x, round(rng.uniform(40, 60), 2)))
        _assert_inside(points)


def test_the_curve_still_passes_through_every_point() -> None:
    points = SERIES["uneven steps"]
    ends = [seg[1][-1] for seg in _segments(smooth_path(points))]
    assert ends == [(float(x), float(y)) for x, y in points[1:]]


def test_the_area_fill_follows_the_same_curve() -> None:
    points = SERIES["a week-end then a jump"]
    assert area_path(points, baseline_y=0, smooth=True).startswith(smooth_path(points))
