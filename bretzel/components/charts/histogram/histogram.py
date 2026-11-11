"""``Histogram`` — raw values counted per tranche, drawn as bars.

It counts the tranches an app would otherwise count by hand, with bounds
a little wrong: a bar per point, four quarters of the scale, irregular
bands « < 9 · 9–13 · 13–15 · ≥ 15 ».

Usage ::

    ui.histogram(marks, x_min=0, x_max=20)                 # a bar per point
    ui.histogram(marks, x_min=0, x_max=20, step=5)         # 0–5 … 15–20
    ui.histogram(means, bins=[0, 9, 13, 15, 20])           # irregular bands
    ui.histogram(marks, x_min=0, x_max=20, show_mean=True) # the mean, marked

The words are the charts' and the inputs' (R1): ``data`` first,
``x_min`` / ``x_max`` cover at least that range (a 21/20 with a bonus
adds a tranche, it does not vanish), ``step`` as on ``ui.slider``,
``bins`` the edges as numpy and matplotlib say it.

A tranche is ``[low, high[``, the last ``[low, high]``: the top of the
scale has its place. A ``step`` of 1 counts per POINT — « 12 » holds
12 and 12,5, and 20/20 is its own bar — the spread a teacher reads.

Built on :class:`BarChart`: the keyboard, the table behind the drawing,
the axis titles, the whole ticks come with it. What is its own: the
tranches, the mean (a vertical mark over the bars) and the click, which
says the tranche's bounds — ``on_item_click(low, high)``, to list who
is in it.
"""

from __future__ import annotations

from bisect import bisect_right
from collections.abc import Callable
from itertools import pairwise
from math import ceil, floor
from typing import Any, ClassVar

from bretzel.components.base import Component, reactive_prop
from bretzel.components.base.attrs import ComponentUsageError
from bretzel.components.charts._svg import format_value
from bretzel.components.charts.bar_chart.bar_chart import BarChart
from bretzel.components.charts.series import bad_point
from bretzel.render import text

#: Past this span, a step of 1 would draw too many bars: about ten
#: tranches instead — ten range labels (« 54–60 ») fit a card, twenty
#: overlap.
POINT_BARS = 40
TRANCHES = 10


def _number(value: Any) -> float:
    if isinstance(value, bool):
        raise bad_point("Histogram", value, "a number")
    return float(value)


def _plain(value: float) -> int | float:
    """A bound as the app would write it: 12, not 12.0 — a click's value."""
    return int(value) if float(value).is_integer() else value


def tranches(
    values: list[float], *, x_min: float | None, x_max: float | None,
    step: float | None, bins: list[float] | None,
) -> list[tuple[float, float, str]]:
    """The tranches, ``(low, high, label)``, in order."""
    if bins is not None:
        if step is not None or x_min is not None or x_max is not None:
            raise ComponentUsageError(
                "Histogram: bins= gives every bound — leave step, x_min and "
                "x_max out.")
        edges = [_number(b) for b in bins]
        if len(edges) < 2 or any(b <= a for a, b in pairwise(edges)):
            raise ComponentUsageError(
                f"Histogram: bins={bins!r} — at least two edges, each above "
                "the one before.")
        outside = [v for v in values if not edges[0] <= v <= edges[-1]]
        if outside:
            raise ComponentUsageError(
                f"Histogram: {outside[0]!r} is outside bins={bins!r}. Widen the "
                "first or the last edge — the bins say every bound.")
        return [(a, b, f"{format_value(a, None)}–{format_value(b, None)}")
                for a, b in pairwise(edges)]
    lo = (min([x_min, *values]) if x_min is not None
          else floor(min(values)) if values else 0.0)
    hi = (max([x_max, *values]) if x_max is not None
          else max(values) if values else lo + 1)
    if step is None:
        step = 1 if hi - lo <= POINT_BARS else ceil((hi - lo) / TRANCHES)
    if step <= 0:
        raise ComponentUsageError(f"Histogram: step={step!r} — a tranche is wider than 0.")
    if step == 1 and float(lo).is_integer():
        return [(k, k + 1, format_value(k, None)) for k in range(int(lo), floor(hi) + 1)]
    n = max(1, ceil((hi - lo) / step))
    out = []
    for i in range(n):
        a = lo + i * step
        b = hi if i == n - 1 else lo + (i + 1) * step
        out.append((a, b, f"{format_value(a, None)}–{format_value(b, None)}"))
    return out


def tranche_of(value: float, cuts: list[tuple[float, float, str]]) -> int:
    """The index of the tranche that holds ``value`` — the last holds its top."""
    lows = [low for low, _high, _label in cuts]
    return min(max(bisect_right(lows, value) - 1, 0), len(cuts) - 1)


class Histogram(BarChart):
    """Raw values counted per tranche — bars, one series."""

    THEME_KEY: ClassVar[str] = "histogram"
    KIND: ClassVar[str] = "chart.histogram"
    # A line at the mean, « Moyenne 12,4 », over the bars.
    show_mean: bool = reactive_prop(default=False, emit_attr=False)

    def __init__(
        self,
        data: Any = None,
        *,
        x_min: float | None = None,
        x_max: float | None = None,
        step: float | None = None,
        bins: list[float] | None = None,
        show_mean: bool | None = None,
        color: str | None = None,
        size: str | None = None,
        width: int | None = None,
        show_values: bool | None = None,
        show_axis: bool | None = None,
        show_gridlines: bool | None = None,
        show_data: bool | None = None,
        y_max: float | None = None,
        x_label: str | None = None,
        y_label: str | None = None,
        on_item_click: Any = None,
        empty_text: str | None = None,
        empty_icon: str | Component | None = "bar-chart-3",
        empty_description: str | Component | None = None,
        empty: Callable[[], Any] | None = None,
        **kwargs: Any,
    ) -> None:
        values = []
        for item in data or []:
            try:
                values.append(_number(item))
            except (TypeError, ValueError):
                raise bad_point("Histogram", item, "a number") from None
        cuts = tranches(values, x_min=x_min, x_max=x_max, step=step, bins=bins)
        counts = [0] * len(cuts)
        for v in values:
            counts[tranche_of(v, cuts)] += 1
        super().__init__(
            [(label, n) for (_low, _high, label), n in zip(cuts, counts, strict=True)]
            if values else [],
            color=color, size=size, width=width, show_values=show_values,
            show_axis=show_axis, show_gridlines=show_gridlines, show_data=show_data,
            y_max=y_max, x_label=x_label, y_label=y_label,
            on_item_click=on_item_click, empty_text=empty_text,
            empty_icon=empty_icon, empty_description=empty_description,
            empty=empty, show_mean=show_mean, **kwargs,
        )
        bounds = {label: {"low": _plain(low), "high": _plain(high)} for low, high, label in cuts}
        # The click says the tranche: its bounds, not its label and count.
        self._item_payload = lambda label, _count: bounds[label]
        # The mean, set here and not in a ``render()`` of its own: the
        # metaclass wraps every class's render, and a second wrap applied
        # ``classes=`` and the root slot twice.
        if self._reactive_values.get("show_mean") and values:
            mean = sum(values) / len(values)
            i = tranche_of(mean, cuts)
            low, high, _label = cuts[i]
            frac = (mean - low) / (high - low) if high > low else 0.5
            self._mark = (i + frac,
                          text("chart.mean", value=format_value(round(mean, 2), None)))
