"""``LineChart`` — continuous x, single or multi-series.

Data shape :

- ``list[number]``           — single series, x = index.
- ``list[(x, y)]``           — single series with explicit numeric x.
- ``list[Series]``           — N series. **All series must share the
  same x values in the same order** (v1 — mismatch raises so the data
  shape gets fixed instead of producing misaligned crosshair markers).

Categorical x (string labels) is **not supported** — that's
``ui.bar_chart``'s territory.

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
  ``10_charts.js`` — the same singleton bar / pie / scatter use, so
  the family reads identically. It anchors **above the plot** (a
  zero-width anchor at the column's screen-x, y = plot top) so it
  never covers the curve. The dots on the curves are the "you are
  here" indicator ; the tooltip is the "what's there".
- For multi-series, the display strings are pre-formatted as
  newline-separated ``x = N`` + one row per series.

Implementation rides ``$bz.charts.lineScope()`` (runtime slab
``10_charts.js``) — tracks ``active`` plus the per-series ``visible``
toggle array driven by the legend. All rendering is server-side SVG
wired with V3 ``bz-*`` directives.

``BINDABLE_PROPS = ()`` — data flows via ``@refreshable``.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime
from typing import Any, ClassVar

from bretzel.components.base import (
    Component,
    reactive_prop,
    stamp_display_none,
)
from bretzel.components.base._wiring import bool_attr, theme_context
from bretzel.components.charts._layers import (
    reject_empty_text_component,
    render_axis_layer,
    render_empty_state,
)
from bretzel.components.charts._svg import (
    _fmt,
    area_path,
    compute_ticks,
    format_value,
    line_path,
    linear_scale,
    nice_domain,
    smooth_path,
)
from bretzel.components.charts.line_chart.theme import LINE_CHART_THEME
from bretzel.components.charts.reference import Reference
from bretzel.components.charts.series import (
    Series,
    coerce_xy_series,
    coloured_slot,
)
from bretzel.core.tree import Element
from bretzel.core.tree import TextNode as TextNode
from bretzel.render import text

_MARGIN_LEFT_AXIS = 48
_MARGIN_LEFT_NO_AXIS = 8
_MARGIN_RIGHT = 12
_MARGIN_TOP = 16
_MARGIN_BOTTOM = 32


class LineChart(Component):
    """Continuous-x line chart with crosshair hover."""

    THEME: ClassVar[dict[str, Any]] = LINE_CHART_THEME
    THEME_KEY: ClassVar[str] = "line_chart"
    IS_CONTAINER: ClassVar[bool] = False
    BINDABLE_PROPS: ClassVar[tuple[str, ...]] = ()
    color: str = reactive_prop(default="primary", emit_attr=False)
    size: str = reactive_prop(default="md", emit_attr=False)
    width: int = reactive_prop(default=600, emit_attr=False)
    # Smooth is the modern default — sharp polylines read as legacy
    # spreadsheet output ; the Catmull-Rom curve looks closer to what
    # users now expect from analytics dashboards. Pass ``smooth=False``
    # for the raw polyline shape (still useful for step-like data).
    smooth: bool = reactive_prop(default=True, emit_attr=False)
    area_fill: bool = reactive_prop(default=False, emit_attr=False)
    show_dots: bool = reactive_prop(default=False, emit_attr=False)
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
        smooth: bool | None = None,
        area_fill: bool | None = None,
        show_dots: bool | None = None,
        show_axis: bool | None = None,
        show_gridlines: bool | None = None,
        show_legend: bool | None = None,
        y_format: Any = None,
        x_format: Any = None,
        y_unit: str | None = None,
        x_unit: str | None = None,
        reference_lines: Any = None,
        empty_text: str | None = None,
        empty_icon: str | None = "line-chart",
        empty_description: str | None = None,
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
        self._reference_lines = _coerce_references(reference_lines)
        # Direct forward: the base layer drops reactive None kwargs (keeps the default).
        super().__init__(
            color=color, size=size, width=width,
            smooth=smooth, area_fill=area_fill,
            show_dots=show_dots, show_axis=show_axis,
            show_gridlines=show_gridlines,
            show_legend=show_legend, empty_text=empty_text,
            **kwargs,
        )

    # ── Render ─────────────────────────────────────────────────────────

    def render(self) -> Element:
        theme, _slots, sizes, size_name, color = theme_context(self)
        palette = theme.get("palette", ("primary",))

        width = int(self._reactive_values.get("width") or 600)
        smooth = bool(self._reactive_values.get("smooth"))
        area_fill = bool(self._reactive_values.get("area_fill"))
        show_dots = bool(self._reactive_values.get("show_dots"))
        show_axis = bool(self._reactive_values.get("show_axis"))
        show_gridlines = bool(self._reactive_values.get("show_gridlines"))
        show_legend = bool(self._reactive_values.get("show_legend"))
        empty_text = self._reactive_values.get("empty_text") or text("chart.empty")

        size_spec = sizes.get(size_name) or sizes.get("md") or {
            "h": 280, "stroke": 1.5, "dot": 3.0, "axis": 12,
        }
        height = int(size_spec["h"])
        stroke_w = float(size_spec["stroke"])
        dot_r = float(size_spec["dot"])
        axis_font = int(size_spec["axis"])

        series = _coerce_series(self._data, palette, default_color=color)

        # Auto-detect date-axis : when the caller passed ``date`` /
        # ``datetime`` x values, swap the x_format default for a
        # span-aware strftime callable (HH:MM for sub-day, "Mon DD"
        # for sub-year, "Mon YYYY" / "YYYY" beyond). Explicit
        # ``x_format=`` always wins so the caller can override.
        x_format_effective, _ = resolve_date_axis_format(
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
        # Single is just ``n_series: 1`` — the legend / visibility
        # plumbing stays off (no ``isVisible`` / ``toggleSeries``), but
        # the column hit-detection, crosshair, active dot and following
        # tooltip are all shared with the multi-series path.
        wrapper_attrs.setdefault(
            "bz-data",
            f"$bz.charts.lineScope({{n_series: {len(series) or 1}}})",
        )

        if not series or not series[0].data:
            return Element(
                tag=self._tag, attrs=wrapper_attrs,
                children=(render_empty_state(
                    self, width=width, height=height,
                    kind=text("chart.line"),
                    message=empty_text, icon=self._empty_icon,
                    description=self._empty_description,
                    escape=self._empty, size_key=size_name,
                ),),
            )

        xmin, xmax = _x_domain(series)
        raw_ymin, raw_ymax = _y_domain(series)
        # Snap the y-domain to the nice tick bracket so the axis line
        # always lands on round numbers AND fully spans the data (no
        # "gridline starts at 60 with data going to 45" surprises).
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

        # Per-index SVG coords + tooltip displays for the hover scope.
        # All series share x values (validated in _coerce_series).
        ref_xs = [float(x) for x, _ in series[0].data]
        x_svgs = [x_scale(x) for x in ref_xs]
        displays = _build_displays(
            series, ref_xs, x_format_effective, self._y_format,
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
            children.append(_render_axis_layer(
                slot, y_ticks, y_scale, plot_left, plot_right,
                axis_font, show_axis, show_gridlines,
                self._y_format, self._y_unit,
            ))

        # Reference lines sit behind the data (rendered before the
        # series paths) so the data line / area paints over them ;
        # the label rides at the right edge so it doesn't compete
        # with the y-axis ticks on the left.
        if self._reference_lines:
            children.append(_render_reference_lines(
                slot, self._reference_lines, y_scale,
                plot_left, plot_right, axis_font,
                self._y_format, self._y_unit,
            ))

        # Per-series paths : area (optional, behind) → line → dots.
        # Each element carries ``bz-show="isVisible(<idx>)"`` so the
        # legend click-to-toggle hides / reveals the whole series
        # group on the client without a server round-trip. All series
        # start visible (init truthy) so no ``display:none`` pre-stamp
        # is needed alongside the ``bz-show``.
        per_series_ys: list[list[float]] = []
        for s_idx2, s in enumerate(series):
            s_color = s.color or None
            scaled = [(x_scale(float(x)), y_scale(float(y))) for x, y in s.data]
            per_series_ys.append([y for _, y in scaled])
            visibility_attrs = (
                {"bz-show": f"isVisible({s_idx2})"}
                if len(series) > 1 else {}
            )
            if area_fill:
                children.append(Element(tag="path", attrs={
                    "class": slot("area", s_color),
                    "fill": f"url(#{gradient_ids[s_idx2]})",
                    "d": area_path(scaled, baseline_y=plot_bottom, smooth=smooth),
                    **visibility_attrs,
                }, children=()))
            children.append(Element(tag="path", attrs={
                "class": slot("line", s_color),
                "d": smooth_path(scaled) if smooth else line_path(scaled),
                "stroke-width": str(stroke_w),
                "stroke-linecap": "round",
                "stroke-linejoin": "round",
                # Normalises ``stroke-dasharray`` / ``-dashoffset`` to
                # the path's geometric length — the entry-draw
                # keyframe (``bz-line-draw``) uses dasharray = 1 so
                # it animates over the full path regardless of how
                # short the polyline actually is.
                "pathLength": "1",
                **visibility_attrs,
            }, children=()))
            if show_dots:
                for cx, cy in scaled:
                    children.append(Element(tag="circle", attrs={
                        "class": slot("dot", s_color),
                        "cx": _fmt(cx), "cy": _fmt(cy), "r": str(dot_r),
                        **visibility_attrs,
                    }, children=()))

        # X-axis labels (numeric ticks across the domain).
        children.append(_render_x_axis_labels(
            slot, xmin, xmax, x_scale, plot_bottom,
            axis_font, x_format_effective, self._x_unit,
        ))

        # Crosshair + active-point markers ride the ``lineScope``
        # ``active`` index — shared by single and multi. The xs / ys
        # arrays are baked verbatim into the V3 expression so the
        # binding doesn't depend on scope-lookup timing or on querying
        # the wrapper's data attrs at evaluation time — the runtime
        # just indexes a plain JS array literal.
        xs_literal = "[" + ",".join(_fmt(x) for x in x_svgs) + "]"

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
            ys_literal = "[" + ",".join(_fmt(y) for y in s_ys) + "]"
            # Visibility on the active dot too — the legend toggle hides
            # the dot when its series is hidden. Single-series skips the
            # ``isVisible`` guard (no legend to toggle it).
            show_expr = (
                f"active >= 0 && isVisible({s_idx})"
                if not single else "active >= 0"
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
        children.append(_render_hit_layer(
            slot, x_svgs, plot_top, plot_bottom, plot_left, plot_right,
            displays,
        ))

        svg_attrs: dict[str, Any] = {
            "class": slot("svg"),
            "viewBox": f"0 0 {width} {height}",
            "width": str(width),
            "height": str(height),
            "role": "img",
            "aria-label": _aria_summary(series),
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
# Helpers — pure functions, no Component access (slot closure passed in)
# ───────────────────────────────────────────────────────────────────────


def _coerce_references(refs: Any) -> list[Reference]:
    """Normalise ``reference_lines=`` into a list of ``Reference``.

    Accepts ``Reference`` instances, ``(value, label)`` 2-tuples, and
    ``(value, label, color)`` 3-tuples. ``None`` / empty → no refs.
    """
    if not refs:
        return []
    out: list[Reference] = []
    for r in refs:
        if isinstance(r, Reference):
            out.append(r)
            continue
        if isinstance(r, (tuple, list)):
            if len(r) >= 3:
                out.append(Reference(value=float(r[0]),
                                     label=str(r[1]),
                                     color=str(r[2]) if r[2] else None))
            elif len(r) >= 2:
                out.append(Reference(value=float(r[0]),
                                     label=str(r[1])))
            elif len(r) == 1:
                out.append(Reference(value=float(r[0])))
    return out


def _is_date_like(x: Any) -> bool:
    """``True`` if ``x`` is a ``date`` / ``datetime`` instance.

    Heuristic for the auto-detect path : if the first x value of the
    first series is date-shaped, every x is converted to its POSIX
    timestamp before scaling, and the axis formatter falls back to a
    locale-friendly date strftime when the caller didn't pass
    ``x_format=`` explicitly.
    """
    return isinstance(x, (date, datetime))




def _auto_date_format(span_seconds: float):
    """Pick an x-axis tick formatter based on the visible time span.

    Same rules every dashboard ships : seconds-precision on tight
    windows, day on multi-day, month on multi-year. Returns a
    callable suitable for ``format_value(..., fmt=callable, unit)``.
    """
    if span_seconds < 60 * 60 * 24:           # < 1 day → "HH:MM"
        fmt = "%H:%M"
    elif span_seconds < 60 * 60 * 24 * 365:   # < 1 an → "Mon DD"
        fmt = "%b %d"
    elif span_seconds < 60 * 60 * 24 * 365 * 5:   # < 5 years → "Mon YYYY"
        fmt = "%b %Y"
    else:                                          # multi-year → "YYYY"
        fmt = "%Y"

    def _fmt_date(moment: datetime) -> str:
        return moment.strftime(fmt)
    return _fmt_date


def as_date_formatter(fn):
    """Make a time-axis formatter receive a ``datetime``.

    On a date axis, the x values are converted to POSIX timestamps
    before being scaled, so ``x_format=`` received a **float** — the only
    handle on the axis's language, and it forced the caller to redo
    ``datetime.fromtimestamp`` themselves before being able to format
    anything (finding [11] of the CRM work). The component knows it is a
    date: it is its job to return it.

    Applies ONLY when the axis is detected as temporal. On a numeric
    axis, ``x_format=`` still receives the number.
    """
    def _wrapped(ts: float) -> str:
        return str(fn(datetime.fromtimestamp(ts)))
    return _wrapped


def resolve_date_axis_format(data: Any, series: list[Series], x_format: Any):
    """The effective x-axis formatter, and whether the axis is temporal.

    Shared by LineChart and ScatterChart, which each had a copy of it
    word for word — and that copy had to be edited on both sides in the
    same commit, which is the signal.

    Three rules, in that order:

    1. a non-temporal axis → we touch nothing, ``x_format=`` receives the
       number as always;
    2. nothing supplied → the automatic formatter, chosen on the visible
       SPAN (HH:MM under a day, "Mon DD" under a year…);
    3. a *callable* — theirs or ours — receives a ``datetime`` and not
       the scaling's POSIX timestamp.

    ⚠️ The point that cost a defect: ``x_format=`` ALSO accepts the
    string shortcuts (``"abbreviated"``, ``"percent"``, ``"currency"``).
    A first version only kept the caller's value if it was callable — so
    a string was **thrown away in silence** on a date axis, and the ticks
    came out identical to the default's. A string does not make much
    sense on a temporal axis, but ignoring it without a word is worse
    than honouring it.
    """
    if not _detect_date_axis(data):
        return x_format, False
    if x_format is None:
        xs_all = [x for s in series for x, _ in s.data]
        x_format = _auto_date_format((max(xs_all) - min(xs_all)) if xs_all else 0.0)
    if callable(x_format):
        x_format = as_date_formatter(x_format)
    return x_format, True


def _coerce_series(
    data: Any, palette: tuple, *, default_color: str,
) -> list[Series]:
    """LineChart's coerce — the shared one : one shared x axis (so the
    series must agree on x), and a bare ``list[number]`` means x=index."""
    return coerce_xy_series(
        data, palette, default_color=default_color, owner="LineChart",
        validate_shared_x=True, allow_index=True,
    )


def _detect_date_axis(data: Any) -> bool:
    """Did the caller pass ``date`` / ``datetime`` x values ?

    Peek at the first sample without coercing it — the actual coerce
    happens in ``_coerce_series``. Single-pass detection on the raw
    input so the auto-format pick can land before scales are built.
    """
    if not data:
        return False
    first = data[0]
    if isinstance(first, Series):
        if not first.data:
            return False
        return _is_date_like(first.data[0][0])
    if isinstance(first, (tuple, list)) and len(first) >= 2:
        return _is_date_like(first[0])
    return False


def _x_domain(series: list[Series]) -> tuple[float, float]:
    xs = [x for s in series for x, _ in s.data]
    if not xs:
        return (0.0, 1.0)
    lo, hi = min(xs), max(xs)
    return (lo, hi) if lo != hi else (lo - 0.5, hi + 0.5)


def _y_domain(series: list[Series]) -> tuple[float, float]:
    ys = [y for s in series for _, y in s.data]
    return nice_domain(ys)


def _aria_summary(series: list[Series]) -> str:
    what = text("chart.points", n=sum(len(s.data) for s in series))
    if len(series) <= 1:
        return text("chart.summary", kind=text("chart.line"), what=what)
    names = ", ".join(s.name for s in series if s.name) or text(
        "chart.series_count", n=len(series))
    return text(
        "chart.summary_across", kind=text("chart.line"), what=what, names=names)


def _build_displays(
    series: list[Series], ref_xs: list[float], x_format, y_format,
    x_unit: str | None = None, y_unit: str | None = None,
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
            y = series[0].data[idx][1]
            out.append(f"{x_label}: {format_value(y, y_format, y_unit)}")
            continue
        parts = [f"x = {x_label}"]
        for s in series:
            y = s.data[idx][1]
            tag = s.name or "Series"
            parts.append(f"{tag}: {format_value(y, y_format, y_unit)}")
        out.append("\n".join(parts))
    return out

def _render_axis_layer(
    slot, ticks: list[float], y_scale, plot_left: float, plot_right: float,
    axis_font: int, show_axis: bool, show_gridlines: bool, y_format,
    y_unit: str | None = None,
) -> Element:
    """LineChart's vertical axis — the shared layer, with this chart's
    structural group class."""
    return render_axis_layer(
        slot, ticks, y_scale, plot_left, plot_right, axis_font,
        show_axis, show_gridlines, y_format, y_unit,
        group_class="bz-line-axes",
    )


def _render_x_axis_labels(
    slot, xmin: float, xmax: float, x_scale, plot_bottom: float,
    axis_font: int, x_format, x_unit: str | None = None,
) -> Element:
    """Numeric ticks across the X domain — Heckbert ~5 ticks.

    ``compute_ticks`` rounds outward to the next nice number, so for a
    raw domain like ``(0, 11)`` it returns ``[0, 5, 10, 15]`` — the
    ``15`` would land past ``plot_right`` and dangle off the chart edge.
    Filter to the in-domain ticks so the axis stops cleanly at the
    data. Same logic applies on the date axis : timestamps past xmax
    would render past the chart.
    """
    ticks = [t for t in compute_ticks(xmin, xmax, target_count=5)
             if xmin <= t <= xmax]
    label_cls = slot("axis_label")
    children: list[Element] = []
    for tick in ticks:
        children.append(Element(tag="text", attrs={
            "class": label_cls,
            "x": _fmt(x_scale(tick)),
            "y": _fmt(plot_bottom + axis_font + 8),
            "font-size": str(axis_font),
            "text-anchor": "middle",
        }, children=(TextNode(format_value(tick, x_format, x_unit)),)))
    return Element(tag="g", attrs={"class": "bz-line-x-labels"},
                   children=tuple(children))


def _render_hit_layer(
    slot, x_svgs: list[float], plot_top: float, plot_bottom: float,
    plot_left: float, plot_right: float, displays: list[str],
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
    hit_cls = slot("hit")
    children: list[Element] = []
    height = plot_bottom - plot_top
    n = len(x_svgs)
    for i, x in enumerate(x_svgs):
        prev_x = (x + x_svgs[i - 1]) / 2 if i > 0 else plot_left
        next_x = (x + x_svgs[i + 1]) / 2 if i < n - 1 else plot_right
        span = next_x - prev_x
        frac = (x - prev_x) / span if span > 0 else 0.5
        children.append(Element(tag="rect", attrs={
            "class": hit_cls,
            "x": _fmt(prev_x),
            "y": _fmt(plot_top),
            "width": _fmt(max(0.0, span)),
            "height": _fmt(height),
            "data-bz-display": displays[i],
            "data-bz-anchor-x": _fmt(frac),
            "bz-on:mouseenter": f"onHover($event, {i})",
            "bz-on:mouseleave": "onLeave()",
        }, children=()))
    return Element(tag="g", attrs={"class": "bz-line-hits"},
                   children=tuple(children))


def _render_reference_lines(
    slot, refs: list[Reference], y_scale,
    plot_left: float, plot_right: float, axis_font: int,
    y_format, y_unit: str | None,
) -> Element:
    """Horizontal dashed lines + right-edge labels for threshold annotations.

    ``color=None`` on a ref falls back to ``"muted"`` so a reference
    line without an explicit colour doesn't compete with the series
    palette. Numeric value formatting matches the y-axis ticks so the
    visual reads as "this is the same scale".
    """
    children: list[Element] = []
    for r in refs:
        colour = r.color or "muted"
        ty = y_scale(float(r.value))
        children.append(Element(tag="line", attrs={
            "class": slot("reference_line", colour),
            "x1": _fmt(plot_left), "x2": _fmt(plot_right),
            "y1": _fmt(ty), "y2": _fmt(ty),
            "stroke-dasharray": "4 4",
        }, children=()))
        # Label sits just above the line at the right edge ; value is
        # shown in parens to keep the eye anchored on the threshold.
        value_str = format_value(float(r.value), y_format, y_unit)
        label = (
            f"{r.label} ({value_str})" if r.label else value_str
        )
        children.append(Element(tag="text", attrs={
            "class": slot("reference_label", colour),
            "x": _fmt(plot_right - 4),
            "y": _fmt(ty - 4),
            "text-anchor": "end",
            "font-size": str(axis_font),
        }, children=(TextNode(label),)))
    return Element(
        tag="g", attrs={"class": "bz-line-refs"},
        children=tuple(children),
    )


def _render_legend(slot, series: list[Series]) -> Element:
    legend_attrs = {"class": slot("legend")}
    label_cls = slot("legend_label")
    item_cls = slot("legend_item")
    children: list[Element] = []
    for s_idx, s in enumerate(series):
        dot_cls = slot("legend_dot", s.color or None)
        # ``bz-on:click`` flips the visibility boolean. V3 has no
        # ``.prevent`` modifier so ``preventDefault`` is inlined ; the
        # button is ``type="button"`` so this is just belt-and-braces.
        # ``bz-class`` MERGES the dim utility onto the static
        # ``legend_item`` classes (never ``bz-attr:class``, which would
        # clobber them) — the item dims to 40 % opacity when off so the
        # user sees which series are hidden at a glance ; the dot keeps
        # full opacity so the colour swatch stays readable as a legend
        # key. All series start visible so ``opacity-100`` is the SSR
        # snapshot — no pre-stamp needed.
        children.append(Element(tag="button", attrs={
            "type": "button",
            "class": item_cls,
            "bz-on:click": (
                f"$event.preventDefault(); toggleSeries({s_idx})"
            ),
            "bz-class": (
                f"isVisible({s_idx}) ? 'opacity-100' : 'opacity-40'"
            ),
            "aria-pressed": "true",
            # Stringify — a raw boolean makes ``bz-attr`` write an empty
            # attr (true) / remove it (false) instead of the "true" /
            # "false" string aria-pressed needs (data-attr trap).
            "bz-attr:aria-pressed": bool_attr(f"isVisible({s_idx})"),
        }, children=(
            Element(tag="span", attrs={"class": dot_cls}, children=()),
            Element(tag="span", attrs={"class": label_cls},
                    children=(TextNode(s.name or text("chart.series")),)),
        )))
    return Element(tag="div", attrs=legend_attrs, children=tuple(children))
