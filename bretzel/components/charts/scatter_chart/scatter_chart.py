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
from bretzel.components.base.events import item_action_attrs
from bretzel.components.base.theme_values import theme_context
from bretzel.components.charts._layers import (
    apply_fixed_width,
    data_table,
    keyboard_attrs,
    plot_svg,
    reject_empty_text_component,
    render_empty_state,
    render_line_axis_layer,
    render_toggle_legend,
    render_x_axis_labels,
    titled,
)
from bretzel.components.charts._svg import (
    PLOT_SPAN,
    _fmt,
    _pct,
    axis_margin,
    compute_ticks,
    format_value,
    joined,
    linear_scale,
    localized_attr,
    nice_domain,
    whole,
    widen,
)
from bretzel.components.charts.reference import (
    coerce_references,
    coerce_x_references,
    render_reference_labels,
    render_reference_lines,
    render_x_reference_labels,
    render_x_reference_lines,
)
from bretzel.components.charts.scatter_chart.theme import SCATTER_CHART_THEME
from bretzel.components.charts.series import (
    Series,
    coerce_xy_series,
    coloured_slot,
    has_points,
    resolve_date_axis_format,
    with_series,
    x_back,
    x_bound,
)
from bretzel.core.tree import Element
from bretzel.render import text
from bretzel.render.context import current_context

# The left margin is at least this, and grows with the widest y label
# (``axis_margin``). The right one is ``_layers.PLOT_MARGIN_RIGHT``.
_MARGIN_LEFT_AXIS = 48
_MARGIN_LEFT_NO_AXIS = 8
_MARGIN_TOP = 16
_MARGIN_BOTTOM = 32


class ScatterChart(Component):
    """Continuous-X-Y scatter plot."""

    THEME: ClassVar[dict[str, Any]] = SCATTER_CHART_THEME
    THEME_KEY: ClassVar[str] = "scatter_chart"
    #: A click on an element of the collection — a point, here — as on
    #: the bars and the slices: ``on_item_click(x, y)``, routed per
    #: element by ``item_action_attrs`` (cf. ``BarChart.EVENTS``).
    EVENTS: ClassVar[tuple[str, ...]] = ("item_click",)
    IS_CONTAINER: ClassVar[bool] = False
    BINDABLE_PROPS: ClassVar[tuple[str, ...]] = ()
    color: str = reactive_prop(default="primary", emit_attr=False)
    size: str = reactive_prop(default="md", emit_attr=False)
    # ``None`` = fill the container; ``N`` = N pixels, capped at the
    # container. Cf. ``_layers.plot_svg``.
    width: int | None = reactive_prop(default=None, emit_attr=False)
    show_axis: bool = reactive_prop(default=True, emit_attr=False)
    show_gridlines: bool = reactive_prop(default=True, emit_attr=False)
    show_legend: bool = reactive_prop(default=True, emit_attr=False)
    # « Voir les données » under the chart: the table behind the
    # drawing, folded (``data_table``). Without it, the table is
    # still there for a screen reader, invisible.
    show_data: bool = reactive_prop(default=False, emit_attr=False)
    # ``None``: the table's « No data », in the page's language — a
    # literal default would freeze it in English.
    empty_text: str | None = reactive_prop(default=None, emit_attr=False)

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
        show_data: bool | None = None,
        y_format: Any = None,
        x_format: Any = None,
        y_unit: str | None = None,
        x_unit: str | None = None,
        y_min: float | None = None,
        y_max: float | None = None,
        x_min: Any = None,
        x_max: Any = None,
        x_label: str | None = None,
        y_label: str | None = None,
        y_reference_lines: Any = None,
        x_reference_lines: Any = None,
        on_item_click: Any = None,
        empty_text: str | None = None,
        empty_icon: str | Component | None = "scatter-chart",
        empty_description: str | Component | None = None,
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
        # The bounds an app asks for: the axis covers them at least.
        # ``x_min`` / ``x_max`` may be dates, like the x values.
        self._y_min, self._y_max = y_min, y_max
        self._x_min = x_bound(type(self).__name__, "x_min", x_min)
        self._x_max = x_bound(type(self).__name__, "x_max", x_max)
        self._x_label, self._y_label = x_label, y_label
        self._on_item_click = on_item_click
        self._reference_lines = coerce_references(
            type(self).__name__, y_reference_lines)
        self._x_reference_lines = coerce_x_references(
            type(self).__name__, x_reference_lines)
        # Direct forward: the base layer drops reactive None kwargs (keeps the default).
        super().__init__(
            color=color, size=size, width=width,
            show_axis=show_axis, show_gridlines=show_gridlines,
            show_legend=show_legend, show_data=show_data, empty_text=empty_text,
            **kwargs,
        )

    # ── Render ─────────────────────────────────────────────────────────

    def render(self) -> Element:
        theme, _slots, sizes, size_name, color = theme_context(self)
        palette = theme.get("palette", ("primary",))

        width = self._reactive_values.get("width")
        show_axis = bool(self._reactive_values.get("show_axis"))
        show_gridlines = bool(self._reactive_values.get("show_gridlines"))
        show_legend = bool(self._reactive_values.get("show_legend"))
        show_data = bool(self._reactive_values.get("show_data"))
        empty_text = self._reactive_values.get("empty_text") or text("chart.empty")

        size_spec = sizes.get(size_name) or sizes.get("md") or {
            "h": 280, "dot_radius": 4.0, "axis_font": 12,
        }
        height = int(size_spec["h"])
        dot_r = float(size_spec["dot_radius"])
        axis_font = int(size_spec["axis_font"])

        series = _coerce_series(self._data, palette, default_color=color)

        def slot(name: str, override: str | None = None) -> str:
            # ``coloured_slot`` adds the colour's BRIDGE: the step's
            # class is the same for every series, it is the bridge that
            # says which is which.
            return coloured_slot(self, name, override, color)

        wrapper_attrs = self.emit_attrs()
        wrapper_attrs["class"] = slot("wrapper")
        apply_fixed_width(wrapper_attrs, width)
        wrapper_attrs.setdefault(
            "bz-data",
            f"$bz.charts.scatterScope({{n_series: {len(series) or 1}}})",
        )

        if not has_points(series):
            return Element(
                tag=self._tag, attrs=wrapper_attrs,
                # An explicit ``kind``: the helper is shared, and an empty
                # scatter must not announce itself as a "Line chart" to
                # the screen reader.
                children=(render_empty_state(
                    height=height,
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

        xmin, xmax = widen(_xy_domain(series, axis="x"),
                           (pt[0] for s in series for pt in s.data),
                           self._x_min, self._x_max)
        if self._x_reference_lines:
            marks = [float(r.value) for r in self._x_reference_lines]
            xmin, xmax = min(xmin, *marks), max(xmax, *marks)
        raw_ymin, raw_ymax = widen(_xy_domain(series, axis="y"),
                                   (pt[1] for s in series for pt in s.data),
                                   self._y_min, self._y_max)
        # Snap y to nice ticks so the axis lands on round numbers and
        # spans the data fully (no half-cut axes — same trick as
        # LineChart / BarChart).
        y_ticks = compute_ticks(raw_ymin, raw_ymax, target_count=5,
                                whole=whole(pt[1] for s in series for pt in s.data))
        ymin = y_ticks[0] if y_ticks else raw_ymin
        ymax = y_ticks[-1] if y_ticks else raw_ymax

        margin_left = (
            axis_margin(
                (format_value(t, self._y_format, self._y_unit) for t in y_ticks),
                axis_font, floor=_MARGIN_LEFT_AXIS,
            )
            if show_axis else _MARGIN_LEFT_NO_AXIS
        )
        plot_top = _MARGIN_TOP
        plot_bottom = height - _MARGIN_BOTTOM
        # x in PERCENT of the plot — cf. ``_svg.PLOT_SPAN``.
        x_scale = linear_scale(xmin, xmax, 0.0, PLOT_SPAN)
        y_scale = linear_scale(ymin, ymax, plot_bottom, plot_top)

        children: list[Element] = []

        if show_gridlines or show_axis:
            children.append(render_line_axis_layer(
                slot, y_ticks, y_scale,
                axis_font, show_axis, show_gridlines,
                self._y_format, self._y_unit,
            ))

        # The line behind the dots, its label in front (after them).
        if self._x_reference_lines:
            children.append(render_x_reference_lines(
                slot, self._x_reference_lines, x_scale, plot_top, plot_bottom,
            ))
        if self._reference_lines:
            children.append(render_reference_lines(
                slot, self._reference_lines, y_scale,
            ))

        # Per-series dot groups — visibility binding rides on the
        # wrapper ``<g>`` so legend toggle hides the whole group at
        # once instead of forcing N attributes per dot.
        back = x_back(self._data)
        ctx = current_context() if self._on_item_click else None
        for s_idx, s in enumerate(series):
            s_color = s.color or None
            group_attrs: dict[str, Any] = {"class": f"bz-scatter-series-{s_idx}"}
            if len(series) > 1:
                # All series start visible → init truthy, no FOUC
                # pre-stamp needed alongside the ``bz-show``.
                group_attrs["bz-show"] = f"isVisible({s_idx})"
            dot_cls = slot("dot", s_color) + (" cursor-pointer" if self._on_item_click else "")
            dot_children: list[Element] = []
            for x, y in s.data:
                click = item_action_attrs(
                    self._on_item_click, event="item_click", dom_event="click",
                    modifier=self._trigger_modifier,
                    payload=with_series({"x": back(x), "y": y}, s, series),
                    owner_id=self.id, ctx=ctx,
                ) if self._on_item_click else {}
                display = _build_display(
                    s, x, y,
                    x_format_effective, self._y_format,
                    self._x_unit, self._y_unit,
                )
                dot_children.append(Element(tag="circle", attrs={
                    "class": dot_cls,
                    "cx": _pct(x_scale(float(x))),
                    "cy": _fmt(y_scale(float(y))),
                    "r": str(dot_r),
                    "data-bz-display": display,
                    **localized_attr(display, "data-bz-display"),
                    "bz-on:mouseenter": "show($event)",
                    "bz-on:mouseleave": "hide()",
                    **click,
                }, children=()))
            children.append(Element(
                tag="g", attrs=group_attrs, children=tuple(dot_children),
            ))

        if self._reference_lines:
            children.append(render_reference_labels(
                slot, self._reference_lines, y_scale, axis_font,
                self._y_format, self._y_unit,
            ))

        if self._x_reference_lines:
            children.append(render_x_reference_labels(
                slot, self._x_reference_lines, x_scale, plot_top, axis_font,
                x_format_effective, self._x_unit,
            ))

        children.append(render_x_axis_labels(
            slot, xmin, xmax, x_scale, plot_bottom,
            axis_font, x_format_effective, self._x_unit,
            whole_x=whole(pt[0] for s in series for pt in s.data), time_axis=date_axis,
        ))

        svg = plot_svg(
            slot, children, height=height, margin_left=margin_left,
            aria_label=_aria_summary(series, date_axis),
        )

        wrapper_children = titled(slot, svg, top=self._y_label, bottom=self._x_label)
        if show_legend and len(series) > 1:
            wrapper_children.append(render_toggle_legend(slot, series))

        multi = len(series) > 1
        wrapper_children.append(data_table(
            slot,
            [*([text("chart.series")] if multi else []),
             self._x_label or "x", self._y_label or text("chart.value")],
            [[*([s.name] if multi else []),
              format_value(float(x), x_format_effective, self._x_unit),
              format_value(float(y), self._y_format, self._y_unit)]
             for s in series for x, y in s.data],
            shown=show_data,
        ))
        keyboard_attrs(wrapper_attrs)
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
        allow_index=False,
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
        return joined(f"{s.name}\n(", x_str, f", {y_str})")
    return joined("(", x_str, f", {y_str})")


def _aria_summary(series: list[Series], date_axis: bool) -> str:
    points = sum(len(s.data) for s in series)
    kind = text("chart.scatter_date_axis" if date_axis else "chart.scatter")
    what = text("chart.points", n=points)
    if len(series) <= 1:
        return text("chart.summary", kind=kind, what=what)
    names = ", ".join(s.name for s in series if s.name) or text(
        "chart.series_count", n=len(series))
    return text("chart.summary_across", kind=kind, what=what, names=names)
