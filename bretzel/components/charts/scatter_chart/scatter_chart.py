"""``ScatterChart`` — continuous X / Y dots, no connecting line.

The companion to ``LineChart`` for analysis use cases : distributions,
correlations, residual plots, dose-response curves. Each ``<circle>``
is a data point ; the hover tooltip (floating, same shared singleton
as bar / pie charts) reads ``data-bz-display`` from the point's own
attributes.

Data shape :

- ``list[(x, y)]``               — single series, numeric x / y.
- ``list[(date, y)]``            — date x ; same auto-detect rule as
  LineChart (``HH:MM`` / ``Mon DD`` / ``Mon YYYY`` / ``YYYY``).
- ``list[Series]``               — N series. Unlike LineChart, the
  series are NOT required to share x values — scatter points are
  independent.

Interactivity :

- Per-dot hover → floating tooltip just above the point.
- Click a legend item → toggle that series' visibility (same V3
  ``bz-data`` chart-scope pattern as LineChart, with the "can't hide
  the last visible series" guard).

``BINDABLE_PROPS = ()`` — data flows via ``@refreshable``.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, ClassVar

from bretzel.components.base import Component, reactive_prop
from bretzel.components.base._wiring import theme_context
from bretzel.components.charts._layers import (
    reject_empty_text_component,
    render_empty_state,
)
from bretzel.components.charts._svg import (
    _fmt,
    compute_ticks,
    format_value,
    linear_scale,
    nice_domain,
)
from bretzel.components.charts.line_chart.line_chart import (
    _coerce_references,
    _render_axis_layer,
    _render_legend,
    _render_reference_lines,
    _render_x_axis_labels,
    resolve_date_axis_format,
)
from bretzel.components.charts.scatter_chart.theme import SCATTER_CHART_THEME
from bretzel.components.charts.series import Series, coerce_xy_series, coloured_slot
from bretzel.core.tree import Element
from bretzel.render import text

_MARGIN_LEFT_AXIS = 48
_MARGIN_LEFT_NO_AXIS = 8
_MARGIN_RIGHT = 12
_MARGIN_TOP = 16
_MARGIN_BOTTOM = 32


class ScatterChart(Component):
    """Continuous-X-Y scatter plot."""

    THEME: ClassVar[dict[str, Any]] = SCATTER_CHART_THEME
    THEME_KEY: ClassVar[str] = "scatter_chart"
    IS_CONTAINER: ClassVar[bool] = False
    BINDABLE_PROPS: ClassVar[tuple[str, ...]] = ()
    color: str = reactive_prop(default="primary", emit_attr=False)
    size: str = reactive_prop(default="md", emit_attr=False)
    width: int = reactive_prop(default=600, emit_attr=False)
    show_axis: bool = reactive_prop(default=True, emit_attr=False)
    show_gridlines: bool = reactive_prop(default=True, emit_attr=False)
    show_legend: bool = reactive_prop(default=True, emit_attr=False)
    empty_text: str = reactive_prop(default="No data", emit_attr=False)

    def __init__(
        self,
        data: Any = None,
        *,
        color: str | None = None,
        size: str | None = None,
        width: int | None = None,
        show_axis: bool | None = None,
        show_gridlines: bool | None = None,
        show_legend: bool | None = None,
        y_format: Any = None,
        x_format: Any = None,
        y_unit: str | None = None,
        x_unit: str | None = None,
        reference_lines: Any = None,
        empty_text: str | None = None,
        empty_icon: str | None = "scatter-chart",
        empty_description: str | None = None,
        empty: Callable[[], Any] | None = None,
        **kwargs: Any,
    ) -> None:
        reject_empty_text_component(empty_text, owner="ScatterChart")
        self._empty_icon = empty_icon
        self._empty_description = empty_description
        self._empty = empty
        self._data = data or []
        self._y_format = y_format
        self._x_format = x_format
        self._y_unit = y_unit
        self._x_unit = x_unit
        self._reference_lines = _coerce_references(reference_lines)
        # Direct forward: the base layer drops reactive None kwargs (keeps the default).
        super().__init__(
            color=color, size=size, width=width,
            show_axis=show_axis, show_gridlines=show_gridlines,
            show_legend=show_legend, empty_text=empty_text,
            **kwargs,
        )

    # ── Render ─────────────────────────────────────────────────────────

    def render(self) -> Element:
        theme, _slots, sizes, size_name, color = theme_context(self)
        palette = theme.get("palette", ("primary",))

        width = int(self._reactive_values.get("width") or 600)
        show_axis = bool(self._reactive_values.get("show_axis"))
        show_gridlines = bool(self._reactive_values.get("show_gridlines"))
        show_legend = bool(self._reactive_values.get("show_legend"))
        empty_text = self._reactive_values.get("empty_text") or "No data"

        size_spec = sizes.get(size_name) or sizes.get("md") or {
            "h": 280, "dot": 4.0, "axis": 12,
        }
        height = int(size_spec["h"])
        dot_r = float(size_spec["dot"])
        axis_font = int(size_spec["axis"])

        series = _coerce_series(self._data, palette, default_color=color)

        def slot(name: str, override: str | None = None) -> str:
            # ``coloured_slot`` adds the colour's BRIDGE: the step's
            # class is the same for every series, it is the bridge that
            # says which is which.
            return coloured_slot(self, name, override, color)

        wrapper_attrs = self.emit_attrs()
        wrapper_attrs["class"] = slot("wrapper")
        wrapper_attrs.setdefault(
            "bz-data",
            f"$bz.charts.scatterScope({{n_series: {len(series) or 1}}})",
        )

        if not series or not any(s.data for s in series):
            return Element(
                tag=self._tag, attrs=wrapper_attrs,
                # An explicit ``kind``: by reusing LineChart's private
                # helper, an empty scatter announced itself as "Line
                # chart" to the screen reader (audit F24).
                children=(render_empty_state(
                    self, width=width, height=height,
                    kind=text("chart.scatter"),
                    message=empty_text, icon=self._empty_icon,
                    description=self._empty_description,
                    escape=self._empty, size_key=size_name,
                ),),
            )

        # Date auto-detect on x — same rule as LineChart.
        x_format_effective, date_axis = resolve_date_axis_format(
            self._data, series, self._x_format,
        )

        xmin, xmax = _xy_domain(series, axis="x")
        raw_ymin, raw_ymax = _xy_domain(series, axis="y")
        # Snap y to nice ticks so the axis lands on round numbers and
        # spans the data fully (no half-cut axes — same trick as
        # LineChart / BarChart).
        y_ticks = compute_ticks(raw_ymin, raw_ymax, target_count=5)
        ymin = y_ticks[0] if y_ticks else raw_ymin
        ymax = y_ticks[-1] if y_ticks else raw_ymax

        margin_left = _MARGIN_LEFT_AXIS if show_axis else _MARGIN_LEFT_NO_AXIS
        plot_left = margin_left
        plot_right = width - _MARGIN_RIGHT
        plot_top = _MARGIN_TOP
        plot_bottom = height - _MARGIN_BOTTOM
        x_scale = linear_scale(xmin, xmax, plot_left, plot_right)
        y_scale = linear_scale(ymin, ymax, plot_bottom, plot_top)

        children: list[Element] = []

        if show_gridlines or show_axis:
            children.append(_render_axis_layer(
                slot, y_ticks, y_scale, plot_left, plot_right,
                axis_font, show_axis, show_gridlines,
                self._y_format, self._y_unit,
            ))

        if self._reference_lines:
            children.append(_render_reference_lines(
                slot, self._reference_lines, y_scale,
                plot_left, plot_right, axis_font,
                self._y_format, self._y_unit,
            ))

        # Per-series dot groups — visibility binding rides on the
        # wrapper ``<g>`` so legend toggle hides the whole group at
        # once instead of forcing N attributes per dot.
        for s_idx, s in enumerate(series):
            s_color = s.color or None
            group_attrs: dict[str, Any] = {"class": f"bz-scatter-series-{s_idx}"}
            if len(series) > 1:
                # All series start visible → init truthy, no FOUC
                # pre-stamp needed alongside the ``bz-show``.
                group_attrs["bz-show"] = f"isVisible({s_idx})"
            dot_cls = slot("dot", s_color)
            dot_children: list[Element] = []
            for x, y in s.data:
                display = _build_display(
                    s, x, y,
                    x_format_effective, self._y_format,
                    self._x_unit, self._y_unit,
                )
                dot_children.append(Element(tag="circle", attrs={
                    "class": dot_cls,
                    "cx": _fmt(x_scale(float(x))),
                    "cy": _fmt(y_scale(float(y))),
                    "r": str(dot_r),
                    "data-bz-display": display,
                    "bz-on:mouseenter": "show($event)",
                    "bz-on:mouseleave": "hide()",
                }, children=()))
            children.append(Element(
                tag="g", attrs=group_attrs, children=tuple(dot_children),
            ))

        children.append(_render_x_axis_labels(
            slot, xmin, xmax, x_scale, plot_bottom,
            axis_font, x_format_effective, self._x_unit,
        ))

        svg_attrs: dict[str, Any] = {
            "class": slot("svg"),
            "viewBox": f"0 0 {width} {height}",
            "width": str(width),
            "height": str(height),
            "role": "img",
            "aria-label": _aria_summary(series, date_axis),
        }
        svg = Element(tag="svg", attrs=svg_attrs, children=tuple(children))

        wrapper_children: list[Element] = [svg]
        if show_legend and len(series) > 1:
            wrapper_children.append(_render_legend(slot, series))

        return Element(
            tag=self._tag, attrs=wrapper_attrs,
            children=tuple(wrapper_children),
        )


# ───────────────────────────────────────────────────────────────────────
# Helpers
# ───────────────────────────────────────────────────────────────────────


def _coerce_series(
    data: Any, palette: tuple, *, default_color: str,
) -> list[Series]:
    """ScatterChart's coerce — the shared one : each cloud is independent
    (no cross-series x alignment), and a bare number carries no x, so it
    is skipped rather than indexed."""
    return coerce_xy_series(
        data, palette, default_color=default_color, owner="ScatterChart",
        validate_shared_x=False, allow_index=False,
    )


def _xy_domain(series: list[Series], *, axis: str) -> tuple[float, float]:
    """Min/max across all series, padded via ``nice_domain``."""
    idx = 0 if axis == "x" else 1
    values = [pt[idx] for s in series for pt in s.data]
    return nice_domain(values)


def _build_display(
    s: Series, x: float, y: float, x_format, y_format,
    x_unit: str | None, y_unit: str | None,
) -> str:
    """Tooltip text for a single dot. Multi-line via ``\\n`` for
    multi-series so the panel renders cleanly with ``whitespace:
    pre-line``."""
    x_str = format_value(x, x_format, x_unit)
    y_str = format_value(y, y_format, y_unit)
    if s.name:
        return f"{s.name}\n({x_str}, {y_str})"
    return f"({x_str}, {y_str})"


def _aria_summary(series: list[Series], date_axis: bool) -> str:
    points = sum(len(s.data) for s in series)
    kind = text("chart.scatter_date_axis" if date_axis else "chart.scatter")
    what = text("chart.points", n=points)
    if len(series) <= 1:
        return text("chart.summary", kind=kind, what=what)
    names = ", ".join(s.name for s in series if s.name) or text(
        "chart.series_count", n=len(series))
    return text("chart.summary_across", kind=kind, what=what, names=names)
