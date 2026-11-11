"""``LineChart`` — continuous x, single or multi-series.

Data shape :

- ``list[number]``           — single series, x = index.
- ``list[(x, y)]``           — single series with explicit numeric x.
- ``list[Series]``           — N series, each on its OWN x values : a
  stock and an index with different holidays draw side by side. The
  hover reads every series on the union of the x values ; a series
  that has no point at a column shows no dot there.

A ``None`` y is a HOLE : the curve stops and starts again after it
(an absent measure, a closed market) — never drawn as zero, never
bridged. A point alone between two holes is drawn as a dot.

Categorical x (string labels) is **not supported** — that's
``ui.bar_chart``'s territory.

Reference lines, two ways :

- ``y_reference_lines=`` — horizontal, at a VALUE (a target, a threshold,
  a price paid) : ``[(1000, "Objectif")]``.
- ``x_reference_lines=`` — vertical, at a MOMENT (a buy, a sale, a
  release) : ``[(date(2026, 10, 13), "achat"), (date(2026, 11, 2),
  "vente", "error")]``. An x is a number or a date, like the x values ;
  the domain widens to show it. For instance a company's price, with
  each buy and sale marked where it happened.

Interactivity — column hover, one path for single and multi :

- Transparent ``<rect>`` overlays span the plot, one per data index,
  bounds set by the midpoint between neighbours so the cursor snaps
  to whichever point is geometrically closest. Hovering anywhere in
  the column works — no need to land on the curve.
- ``onHover(event, idx)`` flips ``active`` on the scope ; the active
  marker dots (one per series) read their ``bz-attr:cx`` /
  ``bz-attr:cy`` from arrays baked into the V3 expression, and a
  vertical crosshair connects them into a readable slice.
- The value itself rides the **shared floating tooltip** from
  ``charts.js`` — the same singleton bar / pie / scatter use, so
  the family reads identically. It anchors **above the plot** (a
  zero-width anchor at the column's screen-x, y = plot top) so it
  never covers the curve. The dots on the curves are the "you are
  here" indicator ; the tooltip is the "what's there".
- For multi-series, the display strings are pre-formatted as
  newline-separated ``x = N`` + one row per series.

Implementation rides ``$bz.charts.lineScope()`` (runtime slab
``charts.js``) — tracks ``active`` plus the per-series ``visible``
toggle array driven by the legend. All rendering is server-side SVG
wired with V3 ``bz-*`` directives.

``BINDABLE_PROPS = ()`` — data flows via ``@refreshable``.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, ClassVar

from bretzel.components.base import (
    Component,
    reactive_prop,
    stamp_display_none,
)
from bretzel.components.base.attrs import ComponentUsageError
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
    area_path,
    axis_margin,
    compute_ticks,
    format_value,
    joined,
    line_path,
    linear_scale,
    localized_attr,
    nice_domain,
    smooth_path,
    whole,
    widen,
)
from bretzel.components.charts.line_chart.theme import LINE_CHART_THEME
from bretzel.components.charts.reference import (
    coerce_references,
    coerce_x_references,
    render_reference_labels,
    render_reference_lines,
    render_x_reference_labels,
    render_x_reference_lines,
)
from bretzel.components.charts.series import (
    Series,
    coerce_xy_series,
    coloured_slot,
    has_points,
    resolve_date_axis_format,
    runs_between_holes,
    x_back,
    x_bound,
)
from bretzel.core.tree import Element
from bretzel.core.tree import TextNode as TextNode
from bretzel.render import text
from bretzel.render.context import current_context

# The left margin is at least this, and grows with the widest y label
# (``axis_margin``). The right one is ``_layers.PLOT_MARGIN_RIGHT``.
_MARGIN_LEFT_AXIS = 48
_MARGIN_LEFT_NO_AXIS = 8
_MARGIN_TOP = 16
_MARGIN_BOTTOM = 32


class LineChart(Component):
    """Continuous-x line chart with crosshair hover."""

    THEME: ClassVar[dict[str, Any]] = LINE_CHART_THEME
    THEME_KEY: ClassVar[str] = "line_chart"
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
    # Smooth is the modern default — sharp polylines read as legacy
    # spreadsheet output ; the monotone curve (``_svg.smooth_path``)
    # looks closer to what users now expect from analytics dashboards,
    # and never passes above or under the data. Pass ``smooth=False``
    # for the raw polyline shape (still useful for step-like data).
    smooth: bool = reactive_prop(default=True, emit_attr=False)
    area_fill: bool = reactive_prop(default=False, emit_attr=False)
    show_dots: bool = reactive_prop(default=False, emit_attr=False)
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
        smooth: bool | None = None,
        area_fill: bool | None = None,
        show_dots: bool | None = None,
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
        empty_icon: str | Component | None = "line-chart",
        empty_description: str | Component | None = None,
        empty: Callable[[], Any] | None = None,
        **kwargs: Any,
    ) -> None:
        reject_empty_text_component(empty_text, owner="LineChart")
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
            smooth=smooth, area_fill=area_fill,
            show_dots=show_dots, show_axis=show_axis,
            show_gridlines=show_gridlines,
            show_legend=show_legend, show_data=show_data, empty_text=empty_text,
            **kwargs,
        )

    # ── Render ─────────────────────────────────────────────────────────

    def render(self) -> Element:
        theme, _slots, sizes, size_name, color = theme_context(self)
        palette = theme.get("palette", ("primary",))

        width = self._reactive_values.get("width")
        smooth = bool(self._reactive_values.get("smooth"))
        area_fill = bool(self._reactive_values.get("area_fill"))
        show_dots = bool(self._reactive_values.get("show_dots"))
        show_axis = bool(self._reactive_values.get("show_axis"))
        show_gridlines = bool(self._reactive_values.get("show_gridlines"))
        show_legend = bool(self._reactive_values.get("show_legend"))
        show_data = bool(self._reactive_values.get("show_data"))
        empty_text = self._reactive_values.get("empty_text") or text("chart.empty")

        size_spec = sizes.get(size_name) or sizes.get("md") or {
            "h": 280, "stroke": 1.5, "dot_radius": 3.0, "axis_font": 12,
        }
        height = int(size_spec["h"])
        stroke_w = float(size_spec["stroke"])
        dot_r = float(size_spec["dot_radius"])
        axis_font = int(size_spec["axis_font"])

        series = _coerce_series(self._data, palette, default_color=color)

        # Auto-detect date-axis : when the caller passed ``date`` /
        # ``datetime`` x values, swap the x_format default for a
        # span-aware strftime callable (HH:MM for sub-day, "Mon DD"
        # for sub-year, "Mon YYYY" / "YYYY" beyond). Explicit
        # ``x_format=`` always wins so the caller can override.
        x_format_effective, date_axis = resolve_date_axis_format(
            self._data, series, self._x_format,
        )

        def slot(name: str, override: str | None = None) -> str:
            # ``coloured_slot`` adds the colour's BRIDGE: the step's
            # class is the same for every series, it is the bridge that
            # says which is which.
            return coloured_slot(self, name, override, color)

        # Unified hover pattern : both single and multi ride full-column
        # hit rects that snap to the nearest x (hover anywhere in the
        # column — no need to land on the line). A vertical crosshair +
        # one active dot per series mark "you are here" ; the shared
        # floating tooltip follows the active column, anchored above the
        # plot so it never covers the curve.
        single = len(series) == 1
        wrapper_attrs = self.emit_attrs()
        wrapper_attrs["class"] = slot("wrapper")
        apply_fixed_width(wrapper_attrs, width)
        # Single is just ``n_series: 1`` — the legend / visibility
        # plumbing stays off (no ``isVisible`` / ``toggleSeries``), but
        # the column hit-detection, crosshair, active dot and following
        # tooltip are all shared with the multi-series path.
        wrapper_attrs.setdefault(
            "bz-data",
            f"$bz.charts.lineScope({{n_series: {len(series) or 1}}})",
        )

        if not has_points(series):
            return Element(
                tag=self._tag, attrs=wrapper_attrs,
                children=(render_empty_state(
                    height=height,
                    kind=text("chart.line"),
                    message=empty_text, icon=self._empty_icon,
                    description=self._empty_description,
                    escape=self._empty, size_key=size_name,
                ),),
            )

        xmin, xmax = widen(_x_domain(series), (x for s in series for x, _ in s.data),
                           self._x_min, self._x_max)
        # A moment marked off the data's span still shows : the axis
        # reaches it, as it reaches an ``x_min``.
        if self._x_reference_lines:
            marks = [float(r.value) for r in self._x_reference_lines]
            xmin, xmax = min(xmin, *marks), max(xmax, *marks)
        raw_ymin, raw_ymax = widen(_y_domain(series), _known_ys(series),
                                   self._y_min, self._y_max)
        # Snap the y-domain to the nice tick bracket so the axis line
        # always lands on round numbers AND fully spans the data (no
        # "gridline starts at 60 with data going to 45" surprises).
        # Counts (every y whole) get whole ticks: no « 0,5 » absence.
        y_ticks = compute_ticks(raw_ymin, raw_ymax, target_count=5,
                                whole=whole(_known_ys(series)))
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

        # Per-column SVG coords + tooltip displays for the hover scope :
        # the columns are the UNION of the series' x values, and each
        # series is read on them (``None`` where it has no point there,
        # or a hole).
        ref_xs, aligned = _align(series)
        x_svgs = [x_scale(x) for x in ref_xs]
        displays = _build_displays(
            series, ref_xs, aligned, x_format_effective, self._y_format,
            self._x_unit, self._y_unit,
        )

        children: list[Element] = []

        # Per-series area gradients live in a single ``<defs>`` block
        # — the ``area`` slot supplies a ``text-{color}`` class so the
        # gradient stops resolve ``currentColor`` to the series colour
        # without baking it into the gradient definition itself.
        gradient_ids: list[str] = []
        if area_fill:
            grad = theme.get("area_gradient",
                             {"top": 0.45, "bottom": 0.10})
            gradient_defs: list[Element] = []
            for s_idx in range(len(series)):
                grad_id = f"{self.id}-area-{s_idx}"
                gradient_ids.append(grad_id)
                s_color = series[s_idx].color or None
                gradient_defs.append(Element(
                    tag="linearGradient",
                    attrs={
                        "id": grad_id,
                        # The gradient itself carries the colour class
                        # — ``<stop currentColor>`` reads its parent
                        # gradient's color, not the painted path's.
                        "class": slot("area_gradient_color", s_color),
                        "x1": "0", "y1": "0", "x2": "0", "y2": "1",
                    },
                    children=(
                        Element(tag="stop", attrs={
                            "offset": "0%",
                            "stop-color": "currentColor",
                            "stop-opacity": str(grad["top"]),
                        }, children=()),
                        Element(tag="stop", attrs={
                            "offset": "100%",
                            "stop-color": "currentColor",
                            "stop-opacity": str(grad["bottom"]),
                        }, children=()),
                    ),
                ))
            children.append(Element(
                tag="defs", attrs={}, children=tuple(gradient_defs),
            ))

        if show_gridlines or show_axis:
            children.append(render_line_axis_layer(
                slot, y_ticks, y_scale,
                axis_font, show_axis, show_gridlines,
                self._y_format, self._y_unit,
            ))

        # Reference LINES sit behind the data (rendered before the
        # series paths) so the data line / area paints over them. Their
        # LABELS are painted after the data — cf.
        # ``render_reference_labels``.
        if self._reference_lines:
            children.append(render_reference_lines(
                slot, self._reference_lines, y_scale,
            ))
        if self._x_reference_lines:
            children.append(render_x_reference_lines(
                slot, self._x_reference_lines, x_scale, plot_top, plot_bottom,
            ))

        # Per-series paths : area (optional, behind) → line → dots.
        # Each element carries ``bz-show="isVisible(<idx>)"`` so the
        # legend click-to-toggle hides / reveals the whole series
        # group on the client without a server round-trip. All series
        # start visible (init truthy) so no ``display:none`` pre-stamp
        # is needed alongside the ``bz-show``.
        per_series_ys: list[list[float | None]] = [
            [None if y is None else y_scale(y) for y in ys] for ys in aligned]
        for s_idx2, s in enumerate(series):
            s_color = s.color or None
            # One run per stretch between two holes : each is its own
            # sub-path, so the curve stops at a hole instead of bridging it.
            runs = [[(x_scale(float(x)), y_scale(float(y))) for x, y in run]
                    for run in runs_between_holes(s.data)]
            scaled = [pt for run in runs for pt in run]
            visibility_attrs = (
                {"bz-show": f"isVisible({s_idx2})"}
                if len(series) > 1 else {}
            )
            paths: list[Element] = []
            if area_fill:
                paths.append(Element(tag="path", attrs={
                    "class": slot("area", s_color),
                    "fill": f"url(#{gradient_ids[s_idx2]})",
                    "d": "".join(area_path(run, baseline_y=plot_bottom, smooth=smooth)
                                 for run in runs if len(run) > 1),
                }, children=()))
            paths.append(Element(tag="path", attrs={
                "class": slot("line", s_color),
                "d": "".join(smooth_path(run) if smooth else line_path(run)
                             for run in runs if len(run) > 1),
                "stroke-width": str(stroke_w),
                "stroke-linecap": "round",
                "stroke-linejoin": "round",
                # The frame below stretches x; the stroke must not
                # follow, or a vertical segment would come out as thick
                # as the chart is wide.
                "vector-effect": "non-scaling-stroke",
            }, children=()))
            children.append(_stretched_frame(height, paths, visibility_attrs))
            # A point alone between two holes has no segment to draw :
            # it is a dot, or it would not show at all.
            alone = [run[0] for run in runs if len(run) == 1]
            for cx, cy in scaled if show_dots else alone:
                children.append(Element(tag="circle", attrs={
                    "class": slot("dot", s_color),
                    "cx": _pct(cx), "cy": _fmt(cy), "r": str(dot_r),
                    **visibility_attrs,
                }, children=()))

        # Reference labels AFTER the data: a label is text to be read,
        # and under a curve (or, on a bar chart, under a bar) it was not.
        # Before the hit layer, which stays on top for the hover.
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

        # X-axis labels (numeric ticks across the domain).
        children.append(render_x_axis_labels(
            slot, xmin, xmax, x_scale, plot_bottom,
            axis_font, x_format_effective, self._x_unit,
            whole_x=whole(x for s in series for x, _ in s.data), time_axis=date_axis,
        ))

        # Crosshair + active-point markers ride the ``lineScope``
        # ``active`` index — shared by single and multi. The xs / ys
        # arrays are baked verbatim into the V3 expression so the
        # binding doesn't depend on scope-lookup timing or on querying
        # the wrapper's data attrs at evaluation time — the runtime
        # just indexes a plain JS array literal.
        # Percent STRINGS: ``bz-attr:x1`` writes them as they are, and
        # ``"37.5%"`` resolves against the plot's width like every other x.
        xs_literal = "[" + ",".join(f"'{_pct(x)}'" for x in x_svgs) + "]"

        # Vertical crosshair line at the active column. Connects the
        # cursor's column to the data so the active dots read as "a
        # slice" instead of scattered points — the fix for "I cannot
        # see the points". ``active`` starts at -1 → hidden at first
        # paint : pre-stamp ``display:none`` to dodge the FOUC.
        crosshair_attrs: dict[str, Any] = {
            "class": slot("crosshair"),
            "bz-attr:x1": f"active >= 0 ? {xs_literal}[active] : -10",
            "bz-attr:x2": f"active >= 0 ? {xs_literal}[active] : -10",
            "y1": _fmt(plot_top), "y2": _fmt(plot_bottom),
            "stroke-dasharray": "4 4",
            "bz-show": "active >= 0",
        }
        stamp_display_none(crosshair_attrs)
        children.append(Element(tag="line", attrs=crosshair_attrs,
                                children=()))

        for s_idx, s_ys in enumerate(per_series_ys):
            s_color = series[s_idx].color or None
            ys_literal = "[" + ",".join(
                "null" if y is None else _fmt(y) for y in s_ys) + "]"
            # Visibility on the active dot too — the legend toggle hides
            # the dot when its series is hidden. Single-series skips the
            # ``isVisible`` guard (no legend to toggle it).
            # A column where the series has no point (a hole, another
            # series' date) shows no dot.
            has = f"{ys_literal}[active] !== null"
            show_expr = (
                f"active >= 0 && {has} && isVisible({s_idx})"
                if not single else f"active >= 0 && {has}"
            )
            dot_attrs: dict[str, Any] = {
                "class": slot("dot_active", s_color),
                "bz-attr:cx": f"active >= 0 ? {xs_literal}[active] : -10",
                "bz-attr:cy": f"active >= 0 ? {ys_literal}[active] : -10",
                "r": str(dot_r + 2.5),
                "bz-show": show_expr,
            }
            stamp_display_none(dot_attrs)
            children.append(Element(tag="circle", attrs=dot_attrs,
                                    children=()))

        # Full-column hit rects drive the ``active`` index (single +
        # multi). Each rect snaps to the nearest x and carries its
        # display string + the data-x anchor fraction the floating
        # tooltip reads to land above the real data column.
        # A click names ONE point: a column of several series holds one
        # per series — which one would it be? Refused, not guessed.
        if self._on_item_click and len(series) > 1:
            raise ComponentUsageError(
                "LineChart: on_item_click on several series — a column holds "
                "one point per series, the click could not say which. Give "
                "one series, or draw the points with ui.scatter_chart.")
        clicks = None
        if self._on_item_click:
            back, ctx = x_back(self._data), current_context()
            clicks = [{} if y is None else item_action_attrs(
                self._on_item_click, event="item_click", dom_event="click",
                modifier=self._trigger_modifier,
                payload={"x": back(x), "y": y},
                owner_id=self.id, ctx=ctx,
            ) for x, y in zip(ref_xs, aligned[0], strict=True)]
        children.append(_render_hit_layer(
            slot, x_svgs, plot_top, plot_bottom, displays, clicks,
        ))

        svg = plot_svg(
            slot, children, height=height, margin_left=margin_left,
            aria_label=_aria_summary(series),
        )

        wrapper_children = titled(slot, svg, top=self._y_label, bottom=self._x_label)
        if show_legend and len(series) > 1:
            wrapper_children.append(render_toggle_legend(slot, series))

        wrapper_children.append(data_table(
            slot,
            [self._x_label or "x",
             *(s.name or self._y_label or text("chart.value") for s in series)],
            [[format_value(x, x_format_effective, self._x_unit),
              *(_NO_VALUE if ys[i] is None
                else format_value(float(ys[i]), self._y_format, self._y_unit)
                for ys in aligned)] for i, x in enumerate(ref_xs)],
            shown=show_data,
        ))
        keyboard_attrs(wrapper_attrs)
        return Element(
            tag=self._tag, attrs=wrapper_attrs,
            children=tuple(wrapper_children),
        )


# ───────────────────────────────────────────────────────────────────────
# Helpers — pure functions, no Component access (slot closure passed in)
# ───────────────────────────────────────────────────────────────────────


def _coerce_series(
    data: Any, palette: tuple, *, default_color: str,
) -> list[Series]:
    """LineChart's coerce — the shared one : a bare ``list[number]``
    means x=index, and a ``None`` y is a hole."""
    return coerce_xy_series(
        data, palette, default_color=default_color, owner="LineChart",
        allow_index=True, allow_gaps=True,
    )


def _x_domain(series: list[Series]) -> tuple[float, float]:
    xs = [x for s in series for x, _ in s.data]
    if not xs:
        return (0.0, 1.0)
    lo, hi = min(xs), max(xs)
    return (lo, hi) if lo != hi else (lo - 0.5, hi + 0.5)


def _y_domain(series: list[Series]) -> tuple[float, float]:
    return nice_domain(_known_ys(series))


#: What a column says for a series that has no point there.
_NO_VALUE = "—"


def _known_ys(series: list[Series]) -> list[float]:
    """Every y that is a value — the holes left out."""
    return [y for s in series for _, y in s.data if y is not None]


def _align(series: list[Series]) -> tuple[list[float], list[list[float | None]]]:
    """The columns — the union of the series' x values, sorted — and
    each series read on them : its y, or ``None`` (a hole, or a column
    where it has no point)."""
    xs = sorted({float(x) for s in series for x, _ in s.data})
    at = {x: i for i, x in enumerate(xs)}
    aligned: list[list[float | None]] = []
    for s in series:
        ys: list[float | None] = [None] * len(xs)
        for x, y in s.data:
            ys[at[float(x)]] = y
        aligned.append(ys)
    return xs, aligned


def _aria_summary(series: list[Series]) -> str:
    what = text("chart.points", n=len(_known_ys(series)))
    if len(series) <= 1:
        return text("chart.summary", kind=text("chart.line"), what=what)
    names = ", ".join(s.name for s in series if s.name) or text(
        "chart.series_count", n=len(series))
    return text(
        "chart.summary_across", kind=text("chart.line"), what=what, names=names)


def _build_displays(
    series: list[Series], ref_xs: list[float], aligned: list[list[float | None]],
    x_format, y_format, x_unit: str | None = None, y_unit: str | None = None,
) -> list[str]:
    """One tooltip string per x index. Single series : compact
    ``"x: y"``. Multi-series : newline-separated ``x = X`` header +
    one row per series. The panel renders with ``whitespace: pre-
    line`` so the newlines turn into a tidy vertical breakdown."""
    out: list[str] = []
    single = len(series) == 1
    for idx, x in enumerate(ref_xs):
        x_label = format_value(x, x_format, x_unit)
        if single:
            y = aligned[0][idx]
            said = _NO_VALUE if y is None else format_value(y, y_format, y_unit)
            out.append(joined(x_label, f": {said}"))
            continue
        rows = []
        for s, ys in zip(series, aligned, strict=True):
            y = ys[idx]
            tag = s.name or text("chart.series")
            said = _NO_VALUE if y is None else format_value(y, y_format, y_unit)
            rows.append(f"\n{tag}: {said}")
        out.append(joined("x = ", x_label, *rows))
    return out


def _stretched_frame(
    height: int, paths: list[Element], attrs: dict[str, Any],
) -> Element:
    """A nested ``<svg>`` whose x runs 0 → ``PLOT_SPAN`` across the plot.

    A path's ``d`` takes no percentage, so the curves are drawn in a
    frame that STRETCHES its x to the plot's width
    (``preserveAspectRatio="none"``) while y stays in pixels (the
    viewBox height is the chart's). What must not stretch is written
    elsewhere: the dots are ``<circle>`` with a percentage ``cx``, in
    the outer svg, so they stay round; the stroke carries
    ``vector-effect: non-scaling-stroke``. The curve itself survives the
    stretch unchanged: a control point of the monotone curve is an
    affine function of the data points, and a stretch is affine.

    ⚠️ That is why the line does not draw itself with a dash
    (``pathLength="1"`` + ``stroke-dasharray: 1``): in
    Chromium, the dash is computed on the UNSTRETCHED length while the
    non-scaling stroke is drawn on the stretched one, so the finished
    line would come out dashed. It reveals by clipping, like the area.
    """
    return Element(tag="svg", attrs={
        "width": "100%",
        "height": str(height),
        "viewBox": f"0 0 {_fmt(PLOT_SPAN)} {height}",
        "preserveAspectRatio": "none",
        "overflow": "visible",
        **attrs,
    }, children=tuple(paths))


def _render_hit_layer(
    slot, x_svgs: list[float], plot_top: float, plot_bottom: float,
    displays: list[str], clicks: list[dict] | None = None,
) -> Element:
    """Invisible per-index rects driving the crosshair scope.

    Each rect spans from the midpoint between the previous and current
    x to the midpoint between the current and next x — so the cursor
    snaps to whichever point is geometrically closest. The first and
    last rects extend to the plot edges so points near the boundary
    stay reachable.

    Each rect carries its tooltip text in ``data-bz-display`` and the
    data-x's fraction within the rect in ``data-bz-anchor-x``. The
    floating tooltip maps that fraction onto the rect's SCREEN bbox
    (scale-robust, no SVG CTM math) to anchor above the real data
    column — same "browser does the screen-coord work" recipe the
    scatter dots use, but the anchor is the column top so a fat hit
    rect still lands the tooltip on the point's x.
    """
    hit_cls = slot("hit") + (" cursor-pointer" if clicks else "")
    children: list[Element] = []
    height = plot_bottom - plot_top
    n = len(x_svgs)
    for i, x in enumerate(x_svgs):
        prev_x = (x + x_svgs[i - 1]) / 2 if i > 0 else 0.0
        next_x = (x + x_svgs[i + 1]) / 2 if i < n - 1 else PLOT_SPAN
        span = next_x - prev_x
        frac = (x - prev_x) / span if span > 0 else 0.5
        children.append(Element(tag="rect", attrs={
            "class": hit_cls,
            "x": _pct(prev_x),
            "y": _fmt(plot_top),
            "width": _pct(max(0.0, span)),
            "height": _fmt(height),
            "data-bz-display": displays[i],
            **localized_attr(displays[i], "data-bz-display"),
            "data-bz-anchor-x": _fmt(frac),
            "bz-on:mouseenter": f"onHover($event, {i})",
            "bz-on:mouseleave": "onLeave()",
            **(clicks[i] if clicks else {}),
        }, children=()))
    return Element(tag="g", attrs={"class": "bz-line-hits"},
                   children=tuple(children))


