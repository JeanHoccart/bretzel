"""``BarChart`` — categorical bars, single or multi-series.

Supports ``vertical`` / ``horizontal`` orientation and ``grouped`` /
``stacked`` / ``stacked_100`` variants. Multi-series grouped draws
side-by-side bars per category.

Data shape :

- ``list[(label, value)]``      — single series shortcut.
- ``list[Series]``              — N series. **All series MUST share the
  same labels in the same order** ; mismatched labels raise
  ``ValueError`` at coerce time (no per-category gap padding).

Interactivity :

- Bars carry ``data-bz-display`` for the tooltip text and dispatch
  ``mouseenter`` / ``mouseleave`` to the chart's tooltip scope
  (``$bz.charts.tooltipScope()`` — runtime slab ``10_charts.js``).
- ``on_item_click=callable(label, value)`` registers a per-bar handler via
  ``functools.partial`` so each rect carries its own signed token. Not
  declared on ``EVENTS`` — the click target is a sub-element, not the root.

``BINDABLE_PROPS = ()`` — data flows through ``@refreshable``.
"""

from __future__ import annotations

from collections.abc import Callable
from functools import partial
from typing import Any, ClassVar

from bretzel.components.base import (
    Component,
    item_action_attrs,
    reactive_prop,
)
from bretzel.components.base._wiring import theme_context
from bretzel.components.charts._layers import (
    reject_empty_text_component,
    render_axis_layer,
    render_empty_state,
)
from bretzel.components.charts._svg import (
    _fmt,
    compute_ticks,
    format_value,
    linear_scale,
)
from bretzel.components.charts.bar_chart.theme import BAR_CHART_THEME
from bretzel.components.charts.line_chart.line_chart import (
    _coerce_references,
    _render_reference_lines,
)
from bretzel.components.charts.series import Series, coloured_slot
from bretzel.core.tree import Element
from bretzel.core.tree import TextNode as TextNode
from bretzel.render import text
from bretzel.render.context import current_context

# Layout constants — picked to balance density and legibility at the
# default 600 × 280 intrinsic size. The plot rectangle is what's left
# after carving out the four margins.
_MARGIN_LEFT_AXIS = 48     # room for Y-tick text (vertical orientation)
_MARGIN_LEFT_HORIZONTAL = 92  # room for category labels (horizontal orientation)
_MARGIN_LEFT_NO_AXIS = 8
_MARGIN_RIGHT = 12
_MARGIN_TOP = 16
_MARGIN_BOTTOM = 32        # room for X-axis labels


class BarChart(Component):
    """Categorical bar chart."""

    THEME: ClassVar[dict[str, Any]] = BAR_CHART_THEME
    THEME_KEY: ClassVar[str] = "bar_chart"
    #: L'event est DÉCLARÉ, et ce n'est pas de la métadonnée.
    #:
    #: Tant qu'il ne l'était pas, `on_item_click=` n'acceptait qu'un callable :
    #: la forme « chaîne d'expression cliente », que tout `on_*` du
    #: framework accepte, y levait un `TypeError` remonté nu de
    #: `functools.partial`, sans nommer le composant ni la prop. Mesuré
    #: le 2026-09-06 sur trois composants livrés
    #: (`.claude/work/audit-declaration-2026-09-06.md`).
    #:
    #: Le routage reste MANUEL — le socle pose l'`hx-post` d'un event
    #: déclaré sur la RACINE, or ici c'est chaque BARRE qui porte le sien,
    #: avec sa donnée. D'où `item_action_attrs`, le routeur partagé des
    #: quatre composants dans ce cas.
    EVENTS: ClassVar[tuple[str, ...]] = ("item_click",)
    IS_CONTAINER: ClassVar[bool] = False
    BINDABLE_PROPS: ClassVar[tuple[str, ...]] = ()
    # Tooltip shows on every bar — the wrapper holds the tooltip scope
    # (``bz-data="$bz.charts.tooltipScope()"``). No EVENTS at the
    # component level ; per-bar clicks register through render().
    color: str = reactive_prop(default="primary", emit_attr=False)
    size: str = reactive_prop(default="md", emit_attr=False)
    width: int = reactive_prop(default=600, emit_attr=False)
    # ``grouped`` (default) = sub-bars side-by-side per category ;
    # ``stacked`` = segments along the value axis (column total reads as
    # a whole) ; ``stacked_100`` = each stack normalised to 100 % for
    # composition comparison. Single-series payloads ignore the variant.
    # ``steps=`` : la valeur nomme un MODE DE TRACÉ, pas un palier de
    # thème — il n'y a donc aucune table à lire, et ``variant="zzz"``
    # rendait à l'identique de ``"grouped"``, en silence. Les trois
    # membres sont testés plus bas (``variant in ("stacked", …)``) ;
    # l'ensemble, lui, se déclare ici, une fois.
    variant: str = reactive_prop(
        default="grouped", emit_attr=False,
        steps=("grouped", "stacked", "stacked_100"),
    )
    # ``vertical`` (default) = categories on X, values up ; ``horizontal``
    # = categories on Y (rows), values right — reads cleaner for long or
    # many (>10) category labels than rotated x-axis text.
    orientation: str = reactive_prop(default="vertical", emit_attr=False)
    show_values: bool = reactive_prop(default=False, emit_attr=False)
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
        variant: str | None = None,
        orientation: str | None = None,
        show_values: bool | None = None,
        show_axis: bool | None = None,
        show_gridlines: bool | None = None,
        show_legend: bool | None = None,
        y_format: Any = None,
        y_unit: str | None = None,
        reference_lines: Any = None,
        on_item_click: Any = None,
        empty_text: str | None = None,
        empty_icon: str | None = "bar-chart-3",
        empty_description: str | None = None,
        empty: Callable[[], Any] | None = None,
        **kwargs: Any,
    ) -> None:
        reject_empty_text_component(empty_text, owner="BarChart")
        self._empty_icon = empty_icon
        self._empty_description = empty_description
        self._empty = empty
        self._data = data or []
        self._y_format = y_format
        self._y_unit = y_unit
        self._reference_lines = _coerce_references(reference_lines)
        self._on_item_click = on_item_click
        # Forward direct : le socle drope les kwargs reactive None (garde le defaut).
        super().__init__(
            color=color, size=size, width=width,
            variant=variant, orientation=orientation,
            show_values=show_values, show_axis=show_axis,
            show_gridlines=show_gridlines,
            show_legend=show_legend, empty_text=empty_text,
            **kwargs,
        )

    # ── Render ─────────────────────────────────────────────────────────

    def render(self) -> Element:
        theme, _slots, sizes, size_name, color = theme_context(self)
        palette = theme.get("palette", ("primary",))

        width = int(self._reactive_values.get("width") or 600)
        variant = self._reactive_values.get("variant") or "grouped"
        orientation = self._reactive_values.get("orientation") or "vertical"
        show_values = bool(self._reactive_values.get("show_values"))
        show_axis = bool(self._reactive_values.get("show_axis"))
        show_gridlines = bool(self._reactive_values.get("show_gridlines"))
        show_legend = bool(self._reactive_values.get("show_legend"))
        empty_text = self._reactive_values.get("empty_text") or text("chart.empty")

        size_spec = sizes.get(size_name) or sizes.get("md") or {
            "h": 280, "axis": 12, "pad": 0.20, "value": 11,
        }
        height = int(size_spec["h"])
        axis_font = int(size_spec["axis"])
        bar_pad = float(size_spec["pad"])
        value_font = int(size_spec["value"])

        series = _coerce_series(self._data, palette, default_color=color)
        labels = _extract_labels(series)

        # Single closure threads compose_class through every helper so
        # they stay pure functions of (slot, geometry) — no Component
        # coupling, no per-bar palette substitution duplication. The
        # optional override carries per-Series colours into the bar /
        # legend-dot slots without leaking the chart's default.
        def slot(name: str, override: str | None = None) -> str:
            # ``coloured_slot`` ajoute le PONT de la couleur : la
            # classe du palier est la même pour toutes les séries,
            # c'est le pont qui dit laquelle est laquelle.
            return coloured_slot(self, name, override, color)

        wrapper_attrs = self.emit_attrs()
        wrapper_attrs["class"] = slot("wrapper")
        wrapper_attrs.setdefault("bz-data", "$bz.charts.tooltipScope()")

        if not labels:
            return Element(
                tag=self._tag, attrs=wrapper_attrs,
                children=(render_empty_state(
                    self, width=width, height=height,
                    kind=text("chart.bar"),
                    message=empty_text, icon=self._empty_icon,
                    description=self._empty_description,
                    escape=self._empty, size_key=size_name,
                ),),
            )

        # Single-series payloads ignore the variant — stacking one
        # series on itself is identical to a regular bar chart.
        multi = len(series) > 1
        stacked = variant in ("stacked", "stacked_100") and multi
        stacked_100 = variant == "stacked_100" and multi
        horizontal = orientation == "horizontal"

        # ``stacked_100`` normalises each category's stack so the
        # value scale is always 0-100, regardless of the underlying
        # numbers. Otherwise reuse the existing domain helpers.
        if stacked_100:
            raw_min, raw_max = 0.0, 100.0
        elif stacked:
            raw_min, raw_max = _stacked_value_domain(series)
        else:
            raw_min, raw_max = _value_domain(series)
        if raw_min == raw_max:
            raw_max = raw_min + 1  # avoid zero-span flat axis
        # Snap to the nice tick bracket so the axis line covers the
        # data fully and lands on round numbers.
        ticks = compute_ticks(raw_min, raw_max, target_count=5)
        vmin = ticks[0] if ticks else raw_min
        vmax = ticks[-1] if ticks else raw_max

        # Horizontal mode needs a wider left margin to fit category
        # labels (which can be multi-word strings ; numeric ticks fit
        # in 48 px but "Customer Acquisition" needs more).
        if horizontal:
            margin_left = (
                _MARGIN_LEFT_HORIZONTAL if show_axis
                else _MARGIN_LEFT_NO_AXIS
            )
        else:
            margin_left = (
                _MARGIN_LEFT_AXIS if show_axis else _MARGIN_LEFT_NO_AXIS
            )
        plot_left = margin_left
        plot_right = width - _MARGIN_RIGHT
        plot_top = _MARGIN_TOP
        plot_bottom = height - _MARGIN_BOTTOM

        # The ``value_scale`` always maps the numeric domain (vmin →
        # vmax) to the value axis ; the axis itself is X in horizontal
        # mode and Y in vertical mode. ``baseline`` is where 0 lands
        # on that scale — bars grow away from it.
        if horizontal:
            value_scale = linear_scale(vmin, vmax, plot_left, plot_right)
        else:
            value_scale = linear_scale(vmin, vmax, plot_bottom, plot_top)
        baseline = value_scale(0)

        children: list[Element] = []

        if show_gridlines or show_axis:
            if horizontal:
                children.append(_render_axis_layer_horizontal(
                    slot, ticks, value_scale, plot_top, plot_bottom,
                    axis_font, show_axis, show_gridlines,
                    self._y_format, self._y_unit,
                ))
            else:
                children.append(_render_axis_layer(
                    slot, ticks, value_scale, plot_left, plot_right,
                    axis_font, show_axis, show_gridlines,
                    self._y_format, self._y_unit,
                ))

        # Reference lines paint BEFORE the bars so the bars cover
        # them ; the line orientation mirrors the chart's : horizontal
        # ``<line>`` in vertical mode, vertical ``<line>`` in
        # horizontal mode.
        if self._reference_lines:
            if horizontal:
                children.append(_render_reference_lines_horizontal(
                    slot, self._reference_lines, value_scale,
                    plot_top, plot_bottom, axis_font,
                    self._y_format, self._y_unit,
                ))
            else:
                children.append(_render_reference_lines(
                    slot, self._reference_lines, value_scale,
                    plot_left, plot_right, axis_font,
                    self._y_format, self._y_unit,
                ))

        # Pick the bars renderer based on orientation × variant matrix.
        if horizontal:
            if stacked_100:
                children.append(_render_stacked_100_bars_horizontal(
                    slot, series, plot_left, plot_top, plot_bottom,
                    value_scale, bar_pad, value_font, show_values,
                    self._y_format, self._y_unit,
                    on_item_click=self._on_item_click, component_id=self.id,
                    modifier=self._trigger_modifier,
                ))
            elif stacked:
                children.append(_render_stacked_bars_horizontal(
                    slot, series, plot_left, plot_top, plot_bottom,
                    value_scale, bar_pad, value_font, show_values,
                    self._y_format, self._y_unit,
                    on_item_click=self._on_item_click, component_id=self.id,
                    modifier=self._trigger_modifier,
                ))
            else:
                children.append(_render_bars_horizontal(
                    slot, series, plot_left, plot_right,
                    plot_top, plot_bottom,
                    baseline, value_scale,
                    bar_pad, value_font, show_values,
                    self._y_format, self._y_unit,
                    on_item_click=self._on_item_click, component_id=self.id,
                    modifier=self._trigger_modifier,
                ))
        else:
            if stacked_100:
                children.append(_render_stacked_100_bars_vertical(
                    slot, series, plot_left, plot_right, value_scale,
                    bar_pad, value_font, show_values,
                    self._y_format, self._y_unit,
                    on_item_click=self._on_item_click, component_id=self.id,
                    modifier=self._trigger_modifier,
                ))
            elif stacked:
                children.append(_render_stacked_bars_layer(
                    slot, series, plot_left, plot_right, baseline,
                    value_scale, bar_pad, value_font, show_values,
                    self._y_format, self._y_unit,
                    on_item_click=self._on_item_click, component_id=self.id,
                    modifier=self._trigger_modifier,
                ))
            else:
                children.append(_render_bars_layer(
                    slot, series, plot_left, plot_right,
                    plot_top, plot_bottom, baseline,
                    value_scale, bar_pad, value_font, show_values,
                    self._y_format, self._y_unit,
                    on_item_click=self._on_item_click, component_id=self.id,
                    modifier=self._trigger_modifier,
                ))

        # Category labels — at the bottom (X axis) in vertical mode,
        # on the left (Y axis) in horizontal mode.
        if horizontal:
            children.append(_render_y_category_labels(
                slot, labels, plot_left, plot_top, plot_bottom, axis_font,
            ))
        else:
            children.append(_render_x_axis_labels(
                slot, labels, plot_left, plot_right, plot_bottom, axis_font,
            ))

        svg_attrs: dict[str, Any] = {
            "class": slot("svg"),
            "viewBox": f"0 0 {width} {height}",
            "width": str(width),
            "height": str(height),
            "role": "img",
            "aria-label": _aria_summary(series, labels),
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
# Module-level helpers — pure ; each takes a ``slot`` callable that
# closes over the chart's ``compose_class`` so palette substitution
# stays palette-correct without leaking ``self`` into helper signatures.
# ───────────────────────────────────────────────────────────────────────


def _coerce_series(
    data: Any, palette: tuple, *, default_color: str,
) -> list[Series]:
    if not data:
        return []
    first = data[0]
    if isinstance(first, Series):
        out: list[Series] = []
        for i, s in enumerate(data):
            colour = s.color or palette[i % len(palette)]
            out.append(Series(name=s.name, data=list(s.data), color=colour))
        # Multi-series must share labels in the same order (no per-category
        # padding). Mismatch raises rather than silently mapping bars under
        # another series' labels.
        if len(out) > 1:
            ref = [item[0] for item in out[0].data]
            for s in out[1:]:
                if [item[0] for item in s.data] != ref:
                    raise ValueError(
                        "BarChart multi-series payloads must share the "
                        "same labels in the same order — got "
                        f"{[item[0] for item in s.data]!r} vs {ref!r}."
                    )
        return out
    pairs: list[tuple] = []
    for item in data:
        if isinstance(item, (tuple, list)) and len(item) >= 2:
            try:
                pairs.append((str(item[0]), float(item[1])))
            except (TypeError, ValueError):
                continue
    return [Series(name="", data=pairs, color=default_color)]


def _extract_labels(series: list[Series]) -> list[str]:
    if not series:
        return []
    return [str(label) for label, _ in series[0].data]


def _stacked_value_domain(series: list[Series]) -> tuple[float, float]:
    """Y-domain for the ``"stacked"`` variant — anchored at 0, spans the
    per-category SUM (not the per-bar max). Positive-only : negative
    segments clamp to 0 contribution so a mixed-sign stack doesn't fold in.
    """
    n_cats = len(series[0].data) if series else 0
    if not n_cats:
        return (0.0, 1.0)
    sums = [0.0] * n_cats
    for s in series:
        for i, (_, v) in enumerate(s.data):
            value = float(v)
            if value > 0:
                sums[i] += value
    hi = max(sums) if sums else 1.0
    return (0.0, hi + hi * 0.05)


def _value_domain(series: list[Series]) -> tuple[float, float]:
    """Anchored at 0 — bars read from a baseline, not a floating min."""
    lo = 0.0
    hi = 0.0
    for s in series:
        for _, v in s.data:
            v = float(v)
            if v < lo:
                lo = v
            elif v > hi:
                hi = v
    span = hi - lo
    if hi > 0:
        hi += span * 0.05
    if lo < 0:
        lo -= span * 0.05
    return (lo, hi)


def _aria_summary(series: list[Series], labels: list[str]) -> str:
    what = text("chart.categories", n=len(labels))
    if len(series) <= 1:
        return text("chart.summary", kind=text("chart.bar"), what=what)
    names = ", ".join(s.name for s in series if s.name) or text(
        "chart.series_count", n=len(series))
    return text(
        "chart.summary_across", kind=text("chart.bar"), what=what, names=names)

def _render_axis_layer(
    slot, ticks: list[float], y_scale, plot_left: float,
    plot_right: float, axis_font: int,
    show_axis: bool, show_gridlines: bool, y_format,
    y_unit: str | None = None,
) -> Element:
    """BarChart's vertical axis — the shared layer, with this chart's
    structural group class. (The HORIZONTAL variant below is a genuinely
    different renderer, not a copy : bottom axis, vertical gridlines.)"""
    return render_axis_layer(
        slot, ticks, y_scale, plot_left, plot_right, axis_font,
        show_axis, show_gridlines, y_format, y_unit,
        group_class="bz-bar-axes",
    )


def _hit_rect(
    *, x: float, y: float, width: float, height: float, display: str,
    on_item_click, ctx, label: Any, value: float, component_id: str,
    modifier: str | None,
) -> Element:
    """Transparent full-band overlay that widens the hover / click target
    to the bar's whole column (its *prolongement*) — a sliver-thin bar is
    still trivial to point at. Carries the tooltip payload + handlers ;
    the visible bar (sibling ``.bz-bar-fill``) is pointer-inert. The
    runtime reads ``.bz-bar-hit`` and anchors the tooltip on that sibling,
    so it still lands on the data point, not the top of the column.
    """
    cls = "bz-bar-hit fill-transparent"
    if on_item_click:
        cls += " cursor-pointer"
    attrs: dict[str, Any] = {
        "class": cls,
        "x": _fmt(x),
        "y": _fmt(y),
        "width": _fmt(width),
        "height": _fmt(height),
        "data-bz-display": display,
        "bz-on:mouseenter": "show($event)",
        "bz-on:mouseleave": "hide()",
    }
    if on_item_click:
        # Les trois formes d'un `on_*`, par le routeur partagé — ce site
        # n'acceptait qu'un callable.
        attrs.update(item_action_attrs(
            on_item_click,
            event="item_click",
            dom_event="click",
            modifier=modifier,
            bind=lambda fn: partial(fn, str(label), value),
            owner_id=component_id,
            ctx=ctx,
        ))
    return Element(tag="rect", attrs=attrs, children=())


def _render_bars_layer(
    slot, series: list[Series],
    plot_left: float, plot_right: float,
    plot_top: float, plot_bottom: float, baseline_y: float, y_scale,
    bar_pad: float, value_font: int, show_values: bool, y_format,
    y_unit: str | None = None,
    *, on_item_click, component_id: str, modifier: str | None,
) -> Element:
    plot_w = plot_right - plot_left
    plot_h = plot_bottom - plot_top
    n_cats = len(series[0].data)
    band_w = plot_w / n_cats
    inner_w = band_w * (1.0 - bar_pad)
    bar_w = inner_w / len(series)
    ctx = current_context() if on_item_click else None
    value_label_cls = slot("value_label") if show_values else ""

    children: list[Element] = []
    # Hover polish — non-hovered bars dim to 80 %, hovered stays at
    # 100 %. The spotlight is driven by the per-column ``group/bar-col``
    # (not the bar's own ``:hover``) because the transparent hit overlay
    # on top intercepts the pointer — cf. ``_hit_rect``.
    hover_states = (
        " group-hover/bars:opacity-80 group-hover/bar-col:!opacity-100"
    )

    for s_idx, s in enumerate(series):
        bar_cls = slot("bar", s.color or None) + " bz-bar-fill" + hover_states
        for cat_idx, (label, value) in enumerate(s.data):
            value = float(value)
            positive = value >= 0
            band_left = plot_left + cat_idx * band_w + (band_w - inner_w) / 2
            x = band_left + s_idx * bar_w
            top_y = y_scale(value) if positive else baseline_y
            bottom_y = baseline_y if positive else y_scale(value)
            h = max(0.0, bottom_y - top_y)
            display = format_value(value, y_format, y_unit)
            prefix = f"{s.name} — " if s.name else ""
            # Column = visible bar (pointer-inert) + optional value label
            # + full-height transparent hit overlay, grouped so the
            # spotlight + tooltip anchor stay column-local.
            col_children: list[Element] = [Element(tag="rect", attrs={
                "class": bar_cls,
                "x": _fmt(x),
                "y": _fmt(top_y),
                "width": _fmt(bar_w),
                "height": _fmt(h),
                "rx": "2",
            }, children=())]

            if show_values:
                text_y = top_y - 4 if positive else bottom_y + value_font + 2
                col_children.append(Element(tag="text", attrs={
                    "class": value_label_cls,
                    "x": _fmt(x + bar_w / 2),
                    "y": _fmt(text_y),
                    "font-size": str(value_font),
                    "text-anchor": "middle",
                }, children=(TextNode(display),)))

            col_children.append(_hit_rect(
                x=x, y=plot_top, width=bar_w, height=plot_h,
                display=f"{prefix}{label}: {display}",
                on_item_click=on_item_click, ctx=ctx, label=label, value=value,
                modifier=modifier,
                component_id=component_id,
            ))
            children.append(Element(tag="g",
                                    attrs={"class": "group/bar-col"},
                                    children=tuple(col_children)))

    return Element(tag="g", attrs={"class": "bz-bars group/bars"},
                   children=tuple(children))


def _render_stacked_bars_layer(
    slot, series: list[Series],
    plot_left: float, plot_right: float, baseline_y: float, y_scale,
    bar_pad: float, value_font: int, show_values: bool, y_format,
    y_unit: str | None = None,
    *, on_item_click, component_id: str, modifier: str | None,
) -> Element:
    """Stacked variant : each category column is one full-width bar split
    into per-series segments, painted bottom-up in declaration order.
    Negative values are skipped per segment (positive-only). The optional
    ``show_values`` label sits atop the stack and shows the column total.
    """
    plot_w = plot_right - plot_left
    n_cats = len(series[0].data)
    band_w = plot_w / n_cats
    bar_w = band_w * (1.0 - bar_pad)
    ctx = current_context() if on_item_click else None
    hover_states = " group-hover/bars:opacity-80 hover:!opacity-100"
    value_label_cls = slot("value_label") if show_values else ""

    children: list[Element] = []
    # Reorganise the data category-major so each column renders its
    # segments in a single sweep — cleaner than nested s_idx / cat_idx
    # iteration and lets the column total fall out of the loop.
    for cat_idx in range(n_cats):
        band_left = plot_left + cat_idx * band_w + (band_w - bar_w) / 2
        accum = 0.0
        label = series[0].data[cat_idx][0]
        for s_idx, s in enumerate(series):
            value = float(s.data[cat_idx][1])
            if value <= 0:
                continue
            seg_bottom_y = y_scale(accum)
            seg_top_y = y_scale(accum + value)
            seg_h = max(0.0, seg_bottom_y - seg_top_y)
            accum += value
            display = format_value(value, y_format, y_unit)
            prefix = f"{s.name} — " if s.name else ""
            bar_cls = slot("bar", s.color or None) + hover_states
            cls = (bar_cls + " cursor-pointer") if on_item_click else bar_cls
            attrs: dict[str, Any] = {
                "class": cls,
                "x": _fmt(band_left),
                "y": _fmt(seg_top_y),
                "width": _fmt(bar_w),
                "height": _fmt(seg_h),
                # No ``rx`` on stacked segments — rounded corners between
                # segments break the stack's visual continuity.
                "data-bz-display": f"{prefix}{label}: {display}",
                "bz-on:mouseenter": "show($event)",
                "bz-on:mouseleave": "hide()",
            }
            if on_item_click:
                attrs.update(item_action_attrs(
                    on_item_click,
                    event="item_click",
                    dom_event="click",
                    modifier=modifier,
                    bind=lambda fn, _l=str(label), _v=value: partial(
                        fn, _l, _v),
                    owner_id=component_id,
                    ctx=ctx,
                ))
            children.append(Element(tag="rect", attrs=attrs, children=()))

        # Column-total label atop the stack — per-segment values would
        # crowd (and are already in the hover tooltip).
        if show_values and accum > 0:
            children.append(Element(tag="text", attrs={
                "class": value_label_cls,
                "x": _fmt(band_left + bar_w / 2),
                "y": _fmt(y_scale(accum) - 4),
                "font-size": str(value_font),
                "text-anchor": "middle",
            }, children=(TextNode(
                format_value(accum, y_format, y_unit),
            ),)))

    return Element(tag="g", attrs={"class": "bz-bars group/bars"},
                   children=tuple(children))


# ───────────────────────────────────────────────────────────────────────
# Horizontal-orientation renderers — the rotational mirror of the
# vertical helpers. Categories sit on the Y axis (rows), values flow
# rightward along the X axis. baseline_x = value_scale(0) is where
# zero lands on the value axis ; bars grow rightward for positive
# values, leftward for negatives.
# ───────────────────────────────────────────────────────────────────────


def _render_bars_horizontal(
    slot, series: list[Series],
    plot_left: float, plot_right: float,
    plot_top: float, plot_bottom: float,
    baseline_x: float, value_scale,
    bar_pad: float, value_font: int, show_values: bool, y_format,
    y_unit: str | None = None,
    *, on_item_click, component_id: str, modifier: str | None,
) -> Element:
    plot_h = plot_bottom - plot_top
    plot_w = plot_right - plot_left
    n_cats = len(series[0].data)
    band_h = plot_h / n_cats
    inner_h = band_h * (1.0 - bar_pad)
    bar_h = inner_h / len(series)
    ctx = current_context() if on_item_click else None
    value_label_cls = slot("value_label") if show_values else ""
    # Spotlight rides the per-row ``group/bar-col`` — the transparent
    # full-width hit overlay on top intercepts the pointer (cf.
    # ``_hit_rect``), so the bar's own ``:hover`` never fires.
    hover_states = (
        " group-hover/bars:opacity-80 group-hover/bar-col:!opacity-100"
    )

    children: list[Element] = []
    for s_idx, s in enumerate(series):
        bar_cls = slot("bar", s.color or None) + " bz-bar-fill" + hover_states
        for cat_idx, (label, value) in enumerate(s.data):
            value = float(value)
            positive = value >= 0
            band_top = plot_top + cat_idx * band_h + (band_h - inner_h) / 2
            y = band_top + s_idx * bar_h
            if positive:
                left_x = baseline_x
                right_x = value_scale(value)
            else:
                left_x = value_scale(value)
                right_x = baseline_x
            w = max(0.0, right_x - left_x)
            display = format_value(value, y_format, y_unit)
            prefix = f"{s.name} — " if s.name else ""
            col_children: list[Element] = [Element(tag="rect", attrs={
                "class": bar_cls,
                "x": _fmt(left_x),
                "y": _fmt(y),
                "width": _fmt(w),
                "height": _fmt(bar_h),
                "rx": "2",
            }, children=())]

            if show_values:
                # Value label at the bar's tip — right of the bar for
                # positive values, left for negative. ``dominant-
                # baseline: middle`` keeps it on the row's center.
                text_x = right_x + 4 if positive else left_x - 4
                text_anchor = "start" if positive else "end"
                col_children.append(Element(tag="text", attrs={
                    "class": value_label_cls,
                    "x": _fmt(text_x),
                    "y": _fmt(y + bar_h / 2),
                    "font-size": str(value_font),
                    "text-anchor": text_anchor,
                    "dominant-baseline": "middle",
                }, children=(TextNode(display),)))

            # Full-width transparent overlay at the sub-bar's own row
            # slice (``bar_h`` tall) — hover / click the whole value-axis
            # extent, not just the drawn bar. Per-series slices don't
            # overlap, so grouped multi-series stays individually hittable.
            col_children.append(_hit_rect(
                x=plot_left, y=y, width=plot_w, height=bar_h,
                display=f"{prefix}{label}: {display}",
                on_item_click=on_item_click, ctx=ctx, label=label, value=value,
                modifier=modifier,
                component_id=component_id,
            ))
            children.append(Element(tag="g",
                                    attrs={"class": "group/bar-col"},
                                    children=tuple(col_children)))

    return Element(tag="g", attrs={"class": "bz-bars group/bars"},
                   children=tuple(children))


def _render_stacked_bars_horizontal(
    slot, series: list[Series],
    plot_left: float, plot_top: float, plot_bottom: float,
    value_scale, bar_pad: float, value_font: int, show_values: bool,
    y_format, y_unit: str | None = None,
    *, on_item_click, component_id: str, modifier: str | None,
) -> Element:
    """Horizontal stacked : one row per category, segments grow rightward
    in declaration order. Positive-only (same contract as vertical)."""
    plot_h = plot_bottom - plot_top
    n_cats = len(series[0].data)
    band_h = plot_h / n_cats
    bar_h = band_h * (1.0 - bar_pad)
    ctx = current_context() if on_item_click else None
    hover_states = " group-hover/bars:opacity-80 hover:!opacity-100"
    value_label_cls = slot("value_label") if show_values else ""

    children: list[Element] = []
    for cat_idx in range(n_cats):
        band_top = plot_top + cat_idx * band_h + (band_h - bar_h) / 2
        accum = 0.0
        label = series[0].data[cat_idx][0]
        for s_idx, s in enumerate(series):
            value = float(s.data[cat_idx][1])
            if value <= 0:
                continue
            seg_left_x = value_scale(accum)
            seg_right_x = value_scale(accum + value)
            seg_w = max(0.0, seg_right_x - seg_left_x)
            accum += value
            display = format_value(value, y_format, y_unit)
            prefix = f"{s.name} — " if s.name else ""
            bar_cls = slot("bar", s.color or None) + hover_states
            cls = (bar_cls + " cursor-pointer") if on_item_click else bar_cls
            attrs: dict[str, Any] = {
                "class": cls,
                "x": _fmt(seg_left_x),
                "y": _fmt(band_top),
                "width": _fmt(seg_w),
                "height": _fmt(bar_h),
                "data-bz-display": f"{prefix}{label}: {display}",
                "bz-on:mouseenter": "show($event)",
                "bz-on:mouseleave": "hide()",
            }
            if on_item_click:
                attrs.update(item_action_attrs(
                    on_item_click,
                    event="item_click",
                    dom_event="click",
                    modifier=modifier,
                    bind=lambda fn, _l=str(label), _v=value: partial(
                        fn, _l, _v),
                    owner_id=component_id,
                    ctx=ctx,
                ))
            children.append(Element(tag="rect", attrs=attrs, children=()))

        if show_values and accum > 0:
            children.append(Element(tag="text", attrs={
                "class": value_label_cls,
                "x": _fmt(value_scale(accum) + 4),
                "y": _fmt(band_top + bar_h / 2),
                "font-size": str(value_font),
                "text-anchor": "start",
                "dominant-baseline": "middle",
            }, children=(TextNode(
                format_value(accum, y_format, y_unit),
            ),)))

    return Element(tag="g", attrs={"class": "bz-bars group/bars"},
                   children=tuple(children))


def _fits_label(extent: float, value_font: int) -> bool:
    """Le segment a-t-il la place d'accueillir une étiquette ``NN%`` ?

    ``extent`` est la dimension du segment le long de l'axe où le texte
    tient le moins — sa hauteur en vertical, sa largeur en horizontal.
    Le seuil vaut la taille de police plus une marge : en-dessous, le
    glyphe déborde du remplissage et les étiquettes des parts voisines
    se télescopent. Une petite part n'est donc pas étiquetée — sa valeur
    reste dans le tooltip au survol.
    """
    return extent >= value_font + 4


def _render_stacked_100_bars_horizontal(
    slot, series: list[Series],
    plot_left: float, plot_top: float, plot_bottom: float,
    value_scale, bar_pad: float, value_font: int, show_values: bool,
    y_format, y_unit: str | None = None,
    *, on_item_click, component_id: str, modifier: str | None,
) -> Element:
    """100 %% normalised horizontal stack — each row sums to 100 %.

    The display strings include both the raw value and the percentage
    so the hover tooltip stays informative even though the segments
    are sized off the normalised ratio.

    ``show_values`` écrit le **pourcentage** au centre de chaque segment
    — pas la valeur brute (elle ne se lit pas dans une pile normalisée,
    et le tooltip la porte déjà), et pas un total en bout de barre (il
    vaut toujours 100). Les segments trop étroits sont sautés.

    (Les deux paramètres étaient dans la signature sans jamais être lus —
    ``show_values=True`` était ignoré en silence sur ce seul variant,
    audit F32.)
    """
    plot_h = plot_bottom - plot_top
    n_cats = len(series[0].data)
    band_h = plot_h / n_cats
    bar_h = band_h * (1.0 - bar_pad)
    ctx = current_context() if on_item_click else None
    hover_states = " group-hover/bars:opacity-80 hover:!opacity-100"

    cat_totals = [
        sum(float(s.data[i][1]) for s in series
            if float(s.data[i][1]) > 0)
        for i in range(n_cats)
    ]

    children: list[Element] = []
    for cat_idx in range(n_cats):
        band_top = plot_top + cat_idx * band_h + (band_h - bar_h) / 2
        total = cat_totals[cat_idx]
        if total <= 0:
            continue
        accum = 0.0
        label = series[0].data[cat_idx][0]
        for s_idx, s in enumerate(series):
            value = float(s.data[cat_idx][1])
            if value <= 0:
                continue
            pct_value = (value / total) * 100.0
            seg_left_x = value_scale(accum)
            seg_right_x = value_scale(accum + pct_value)
            seg_w = max(0.0, seg_right_x - seg_left_x)
            accum += pct_value
            display = (
                f"{round(pct_value)}% "
                f"({format_value(value, y_format, y_unit)})"
            )
            prefix = f"{s.name} — " if s.name else ""
            bar_cls = slot("bar", s.color or None) + hover_states
            cls = (bar_cls + " cursor-pointer") if on_item_click else bar_cls
            attrs: dict[str, Any] = {
                "class": cls,
                "x": _fmt(seg_left_x),
                "y": _fmt(band_top),
                "width": _fmt(seg_w),
                "height": _fmt(bar_h),
                "data-bz-display": f"{prefix}{label}: {display}",
                "bz-on:mouseenter": "show($event)",
                "bz-on:mouseleave": "hide()",
            }
            if on_item_click:
                attrs.update(item_action_attrs(
                    on_item_click,
                    event="item_click",
                    dom_event="click",
                    modifier=modifier,
                    bind=lambda fn, _l=str(label), _v=value: partial(
                        fn, _l, _v),
                    owner_id=component_id,
                    ctx=ctx,
                ))
            children.append(Element(tag="rect", attrs=attrs, children=()))
            if show_values and _fits_label(seg_w, value_font):
                children.append(Element(tag="text", attrs={
                    "class": slot("segment_label", s.color or None),
                    "x": _fmt(seg_left_x + seg_w / 2),
                    "y": _fmt(band_top + bar_h / 2),
                    "font-size": str(value_font),
                    "text-anchor": "middle",
                    "dominant-baseline": "central",
                }, children=(TextNode(f"{round(pct_value)}%"),)))

    return Element(tag="g", attrs={"class": "bz-bars group/bars"},
                   children=tuple(children))


def _render_stacked_100_bars_vertical(
    slot, series: list[Series],
    plot_left: float, plot_right: float, value_scale,
    bar_pad: float, value_font: int, show_values: bool,
    y_format, y_unit: str | None = None,
    *, on_item_click, component_id: str, modifier: str | None,
) -> Element:
    """100 %% normalised vertical stack — each column sums to 100 %.

    ``show_values`` : comme son pendant horizontal — le pourcentage au
    centre de chaque segment, les parts trop courtes sautées.
    """
    plot_w = plot_right - plot_left
    n_cats = len(series[0].data)
    band_w = plot_w / n_cats
    bar_w = band_w * (1.0 - bar_pad)
    ctx = current_context() if on_item_click else None
    hover_states = " group-hover/bars:opacity-80 hover:!opacity-100"

    cat_totals = [
        sum(float(s.data[i][1]) for s in series
            if float(s.data[i][1]) > 0)
        for i in range(n_cats)
    ]

    children: list[Element] = []
    for cat_idx in range(n_cats):
        band_left = plot_left + cat_idx * band_w + (band_w - bar_w) / 2
        total = cat_totals[cat_idx]
        if total <= 0:
            continue
        accum = 0.0
        label = series[0].data[cat_idx][0]
        for s_idx, s in enumerate(series):
            value = float(s.data[cat_idx][1])
            if value <= 0:
                continue
            pct_value = (value / total) * 100.0
            seg_bottom_y = value_scale(accum)
            seg_top_y = value_scale(accum + pct_value)
            seg_h = max(0.0, seg_bottom_y - seg_top_y)
            accum += pct_value
            display = (
                f"{round(pct_value)}% "
                f"({format_value(value, y_format, y_unit)})"
            )
            prefix = f"{s.name} — " if s.name else ""
            bar_cls = slot("bar", s.color or None) + hover_states
            cls = (bar_cls + " cursor-pointer") if on_item_click else bar_cls
            attrs: dict[str, Any] = {
                "class": cls,
                "x": _fmt(band_left),
                "y": _fmt(seg_top_y),
                "width": _fmt(bar_w),
                "height": _fmt(seg_h),
                "data-bz-display": f"{prefix}{label}: {display}",
                "bz-on:mouseenter": "show($event)",
                "bz-on:mouseleave": "hide()",
            }
            if on_item_click:
                attrs.update(item_action_attrs(
                    on_item_click,
                    event="item_click",
                    dom_event="click",
                    modifier=modifier,
                    bind=lambda fn, _l=str(label), _v=value: partial(
                        fn, _l, _v),
                    owner_id=component_id,
                    ctx=ctx,
                ))
            children.append(Element(tag="rect", attrs=attrs, children=()))
            if show_values and _fits_label(seg_h, value_font):
                children.append(Element(tag="text", attrs={
                    "class": slot("segment_label", s.color or None),
                    "x": _fmt(band_left + bar_w / 2),
                    "y": _fmt(seg_top_y + seg_h / 2),
                    "font-size": str(value_font),
                    "text-anchor": "middle",
                    "dominant-baseline": "central",
                }, children=(TextNode(f"{round(pct_value)}%"),)))

    return Element(tag="g", attrs={"class": "bz-bars group/bars"},
                   children=tuple(children))


# ───────────────────────────────────────────────────────────────────────
# Horizontal axes + category labels
# ───────────────────────────────────────────────────────────────────────


def _render_axis_layer_horizontal(
    slot, ticks: list[float], value_scale, plot_top: float,
    plot_bottom: float, axis_font: int,
    show_axis: bool, show_gridlines: bool, y_format,
    y_unit: str | None = None,
) -> Element:
    """Horizontal-orientation axes — value axis at the bottom (X),
    gridlines run vertical."""
    gridline_cls = slot("gridline")
    axis_cls = slot("axis")
    label_cls = slot("axis_label")
    children: list[Element] = []
    if show_axis:
        # Bottom value-axis line spans from leftmost to rightmost tick.
        children.append(Element(tag="line", attrs={
            "class": axis_cls,
            "x1": _fmt(value_scale(ticks[0])),
            "x2": _fmt(value_scale(ticks[-1])),
            "y1": _fmt(plot_bottom),
            "y2": _fmt(plot_bottom),
        }, children=()))
    for tick in ticks:
        tx = value_scale(tick)
        if show_gridlines:
            children.append(Element(tag="line", attrs={
                "class": gridline_cls,
                "x1": _fmt(tx), "x2": _fmt(tx),
                "y1": _fmt(plot_top), "y2": _fmt(plot_bottom),
            }, children=()))
        if show_axis:
            children.append(Element(tag="text", attrs={
                "class": label_cls,
                "x": _fmt(tx),
                "y": _fmt(plot_bottom + axis_font + 8),
                "font-size": str(axis_font),
                "text-anchor": "middle",
            }, children=(TextNode(format_value(tick, y_format, y_unit)),)))
    return Element(tag="g", attrs={"class": "bz-bar-axes"},
                   children=tuple(children))


def _render_y_category_labels(
    slot, labels: list[str], plot_left: float, plot_top: float,
    plot_bottom: float, axis_font: int,
) -> Element:
    """Category labels stacked on the Y axis — one per row, right-
    aligned to the plot's left edge so they read into the rows they
    label.
    """
    plot_h = plot_bottom - plot_top
    band_h = plot_h / len(labels)
    label_cls = slot("axis_label")
    children: list[Element] = []
    for i, label in enumerate(labels):
        children.append(Element(tag="text", attrs={
            "class": label_cls,
            "x": _fmt(plot_left - 6),
            "y": _fmt(plot_top + (i + 0.5) * band_h),
            "font-size": str(axis_font),
            "text-anchor": "end",
            "dominant-baseline": "middle",
        }, children=(TextNode(str(label)),)))
    return Element(tag="g", attrs={"class": "bz-bar-y-labels"},
                   children=tuple(children))


def _render_reference_lines_horizontal(
    slot, refs, value_scale,
    plot_top: float, plot_bottom: float, axis_font: int,
    y_format, y_unit: str | None,
) -> Element:
    """Vertical reference lines for horizontal-orientation charts — at
    ``value_scale(value)`` on the X axis, label rides at the top."""
    children: list[Element] = []
    for r in refs:
        colour = r.color or "muted"
        tx = value_scale(float(r.value))
        children.append(Element(tag="line", attrs={
            "class": slot("reference_line", colour),
            "x1": _fmt(tx), "x2": _fmt(tx),
            "y1": _fmt(plot_top), "y2": _fmt(plot_bottom),
            "stroke-dasharray": "4 4",
        }, children=()))
        value_str = format_value(float(r.value), y_format, y_unit)
        label = (
            f"{r.label} ({value_str})" if r.label else value_str
        )
        # Label sits just above the line at the top of the plot,
        # rotated 0 (horizontal text). text-anchor: start so it
        # extends to the right of the reference line.
        children.append(Element(tag="text", attrs={
            "class": slot("reference_label", colour),
            "x": _fmt(tx + 4),
            "y": _fmt(plot_top + axis_font),
            "text-anchor": "start",
            "font-size": str(axis_font),
        }, children=(TextNode(label),)))
    return Element(
        tag="g", attrs={"class": "bz-bar-refs"},
        children=tuple(children),
    )


def _render_x_axis_labels(
    slot, labels: list[str], plot_left: float, plot_right: float,
    plot_bottom: float, axis_font: int,
) -> Element:
    plot_w = plot_right - plot_left
    band_w = plot_w / len(labels)
    label_cls = slot("axis_label")
    children: list[Element] = []
    for i, label in enumerate(labels):
        children.append(Element(tag="text", attrs={
            "class": label_cls,
            "x": _fmt(plot_left + (i + 0.5) * band_w),
            "y": _fmt(plot_bottom + axis_font + 8),
            "font-size": str(axis_font),
            "text-anchor": "middle",
        }, children=(TextNode(str(label)),)))
    return Element(tag="g", attrs={"class": "bz-bar-x-labels"},
                   children=tuple(children))


def _render_legend(slot, series: list[Series]) -> Element:
    legend_attrs = {"class": slot("legend")}
    label_cls = slot("legend_label")
    children: list[Element] = []
    for s in series:
        dot_cls = slot("legend_dot", s.color or None)
        children.append(Element(tag="div", attrs={
            "class": "flex items-center gap-2",
        }, children=(
            Element(tag="span", attrs={"class": dot_cls}, children=()),
            Element(tag="span", attrs={"class": label_cls},
                    children=(TextNode(s.name or text("chart.series")),)),
        )))
    return Element(tag="div", attrs=legend_attrs, children=tuple(children))
