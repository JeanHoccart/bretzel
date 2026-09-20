"""``PieChart`` — pie or donut, optional arc labels + centre text.

Data shape : ``list[(label, value)]`` — pies are intrinsically single-
distribution, no series. Values are summed for the total ; per-slice
percentages are derived. Zero / negative values are silently skipped
(a negative-area wedge doesn't read). **Percentages re-normalise over
the kept slices** — dropping a negative doesn't reserve space for it.

``center_text`` only renders when ``variant="donut"`` (no centre void
on a solid pie). Pass it for KPI rings — typically a total or a headline
number that summarises what the slices break down.

Interactivity : per-slice hover via ``$bz.charts.tooltipScope()``
(same factory bar_chart uses, wired with V3 ``bz-on:`` directives) —
each ``<path>`` carries a pre-formatted ``data-bz-display`` of the
form ``"Label: value (NN%)"``. ``on_item_click(label, value)`` registers a
per-slice partial at render time so each path carries its own
HMAC-signed token (mirrors bar_chart's per-bar pattern).

``BINDABLE_PROPS = ()`` — data flows via ``@refreshable``.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from functools import partial
from typing import Any, ClassVar

from bretzel.components.base import (
    Component,
    item_action_attrs,
    reactive_prop,
)
from bretzel.components.charts._layers import (
    reject_empty_text_component,
    render_empty_state,
    render_static_legend,
)
from bretzel.components.charts._svg import _fmt, arc_path, format_value
from bretzel.components.charts.pie_chart.theme import PIE_CHART_THEME
from bretzel.components.charts.series import coloured_slot
from bretzel.core.tree import Element
from bretzel.core.tree import TextNode as TextNode
from bretzel.render import text
from bretzel.render.context import current_context

# Inner-radius fraction for the ``donut`` variant. Kept off the API surface
# — picked to land between Material's 60% donut and Chart.js's 75%.
# Tighter pie reads as solid ; looser hollows out the center too much.
_DONUT_INNER_FRAC = 0.62


class PieChart(Component):
    """Pie or donut chart."""

    THEME: ClassVar[dict[str, Any]] = PIE_CHART_THEME
    THEME_KEY: ClassVar[str] = "pie_chart"
    #: The event is DECLARED, and it is not metadata.
    #:
    #: As long as it was not, `on_item_click=` accepted only a callable:
    #: the "client expression string" shape, which every framework `on_*`
    #: accepts, raised a `TypeError` surfaced bare from
    #: `functools.partial`, naming neither the component nor the prop.
    #: Measured on 2026-09-06 on three shipped components
    #: (`.claude/work/audit-declaration-2026-09-06.md`).
    #:
    #: The routing stays MANUAL — the base layer sets a declared event's
    #: `hx-post` on the ROOT, yet here it is each SLICE that carries its
    #: own, with its data. Hence `item_action_attrs`, the shared router
    #: of the four components in that case.
    EVENTS: ClassVar[tuple[str, ...]] = ("item_click",)
    IS_CONTAINER: ClassVar[bool] = False
    BINDABLE_PROPS: ClassVar[tuple[str, ...]] = ()
    size: str = reactive_prop(default="md", emit_attr=False)
    # Chart shape lives under ``variant`` — same idiom as BarChart's
    # ``grouped`` / ``stacked``. ``"pie"`` (default) is a solid disc ;
    # ``"donut"`` hollows out the centre (and unlocks ``center_text`` for
    # a KPI ring).
    # ``steps=``: a plotting mode, not a step — no table to read, so
    # ``variant="zzz"`` fell back on ``"pie"`` without a word.
    variant: str = reactive_prop(
        default="pie", emit_attr=False, steps=("pie", "donut"),
    )
    show_labels: bool = reactive_prop(default=False, emit_attr=False)
    show_legend: bool = reactive_prop(default=True, emit_attr=False)
    center_text: str = reactive_prop(default="", emit_attr=False)
    empty_text: str = reactive_prop(default="No data", emit_attr=False)

    def __init__(
        self,
        data: Any = None,
        *,
        colors: Any = None,
        size: str | None = None,
        variant: str | None = None,
        show_labels: bool | None = None,
        show_legend: bool | None = None,
        center_text: str | None = None,
        value_format: Any = None,
        value_unit: str | None = None,
        on_item_click: Any = None,
        empty_text: str | None = None,
        empty_icon: str | None = "pie-chart",
        empty_description: str | None = None,
        empty: Callable[[], Any] | None = None,
        **kwargs: Any,
    ) -> None:
        reject_empty_text_component(empty_text, owner="PieChart")
        self._empty_icon = empty_icon
        self._empty_description = empty_description
        self._empty = empty
        self._data = data or []
        self._colors = list(colors) if colors else None
        self._value_format = value_format
        self._value_unit = value_unit
        self._on_item_click = on_item_click
        # Direct forward: the base layer drops reactive None kwargs (keeps the default).
        super().__init__(
            size=size, variant=variant,
            show_labels=show_labels, show_legend=show_legend,
            center_text=center_text, empty_text=empty_text,
            **kwargs,
        )

    # ── Render ─────────────────────────────────────────────────────────

    def render(self) -> Element:
        theme = self._resolved_theme()
        sizes = theme.get("sizes", {})
        palette = self._colors or list(theme.get("palette", ("primary",)))

        size_name = self._reactive_values.get("size") or "md"
        is_donut = (self._reactive_values.get("variant") or "pie") == "donut"
        show_labels = bool(self._reactive_values.get("show_labels"))
        show_legend = bool(self._reactive_values.get("show_legend"))
        center_text = self._reactive_values.get("center_text") or ""
        empty_text = self._reactive_values.get("empty_text") or "No data"

        size_spec = sizes.get(size_name) or sizes.get("md") or {
            "h": 280, "label": 12, "center": 22,
        }
        side = int(size_spec["h"])
        label_font = int(size_spec["label"])
        center_font = int(size_spec["center"])

        slices = _coerce_slices(self._data)

        def slot(name: str, override: str | None = None) -> str:
            # ``coloured_slot`` adds the colour's BRIDGE: the step's
            # class is the same for every series, it is the bridge that
            # says which is which.
            return coloured_slot(self, name, override, palette[0])

        wrapper_attrs = self.emit_attrs()
        wrapper_attrs["class"] = slot("wrapper")
        wrapper_attrs.setdefault("bz-data", "$bz.charts.tooltipScope()")

        if not slices:
            return Element(
                tag=self._tag, attrs=wrapper_attrs,
                children=(render_empty_state(
                    self, width=side, height=side,
                    kind=text("chart.donut") if is_donut else text("chart.pie"),
                    message=empty_text, icon=self._empty_icon,
                    description=self._empty_description,
                    escape=self._empty, size_key=size_name,
                ),),
            )

        # Reserve a small margin so the optional outside labels don't
        # clip the SVG box.
        pad = 18 if show_labels else 4
        cx = cy = side / 2
        radius = (side / 2) - pad
        inner_radius = radius * _DONUT_INNER_FRAC if is_donut else 0.0
        total = sum(v for _, v in slices) or 1.0

        ctx = current_context() if self._on_item_click else None
        children: list[Element] = []

        start = 0.0
        for idx, (label, value) in enumerate(slices):
            colour = palette[idx % len(palette)]
            sweep = (value / total) * 2 * math.pi
            end = start + sweep
            pct = round((value / total) * 100)
            display_value = format_value(
                value, self._value_format, self._value_unit,
            )
            display = f"{label}: {display_value} ({pct}%)"

            slice_cls = slot("slice", colour)
            # Hover polish — non-hovered slices dim to 80 %, hovered
            # stays at 100 % via ``hover:!opacity-100``. Subtle pop
            # that keeps the other slices' share readable.
            slice_cls += (
                " group-hover/pie:opacity-80 hover:!opacity-100"
            )
            # Tooltip anchor : the wedge centroid (mid-angle, mid-radius)
            # in SVG-space. A ``<path>`` bbox spans the whole envelope, so
            # without this the runtime falls back to the cursor and the
            # tooltip drifts as the pointer moves inside the slice. Emitting
            # a fixed point per slice pins the tooltip to the same spot every
            # hover (same radial position the outside labels would use).
            anchor_mid = start + sweep / 2
            anchor_r = (
                (radius + inner_radius) / 2 if is_donut else radius * 0.65
            )
            anchor_x = cx + anchor_r * math.cos(anchor_mid - math.pi / 2)
            anchor_y = cy + anchor_r * math.sin(anchor_mid - math.pi / 2)
            slice_attrs: dict[str, Any] = {
                "class": slice_cls + " cursor-pointer" if self._on_item_click
                         else slice_cls,
                "d": arc_path(cx, cy, radius, start, end,
                              inner_radius=inner_radius),
                "stroke-width": "1.5",
                # ``round`` instead of the default ``miter`` : narrow
                # slices (1-5 %) hit a centre angle so acute that the
                # miter overshoots the miter-limit and the corner gets
                # clipped, leaving triangular notches at the centre.
                # Rounding the inner join sidesteps the entire issue.
                "stroke-linejoin": "round",
                "data-bz-display": display,
                "data-bz-ax": _fmt(anchor_x),
                "data-bz-ay": _fmt(anchor_y),
                "bz-on:mouseenter": "show($event)",
                "bz-on:mouseleave": "hide()",
            }
            if self._on_item_click:
                # The three shapes of an `on_*`, through the shared
                # router. This site accepted only a callable: a string
                # raised a bare `TypeError` from `partial`.
                slice_attrs.update(item_action_attrs(
                    self._on_item_click,
                    event="item_click",
                    dom_event="click",
                    # `debounce=` / `throttle=`: the base layer applies
                    # them only to the ROOT's action.
                    modifier=self._trigger_modifier,
                    bind=lambda fn, _l=str(label), _v=float(value): partial(
                        fn, _l, _v),
                    owner_id=self.id,
                    ctx=ctx,
                ))
            children.append(Element(tag="path", attrs=slice_attrs, children=()))

            # 0.08 rad ≈ 4.6° — below this a centred "NN%" overlaps the
            # neighbouring slice's label and reads as noise.
            if show_labels and sweep > 0.08:
                mid = start + sweep / 2
                label_r = (
                    (radius + inner_radius) / 2 if is_donut
                    else radius * 0.65
                )
                lx = cx + label_r * math.cos(mid - math.pi / 2)
                ly = cy + label_r * math.sin(mid - math.pi / 2)
                children.append(Element(tag="text", attrs={
                    "class": slot("slice_label"),
                    "x": _fmt(lx),
                    "y": _fmt(ly),
                    "font-size": str(label_font),
                    "text-anchor": "middle",
                    "dominant-baseline": "middle",
                }, children=(TextNode(f"{pct}%"),)))

            start = end

        if is_donut and center_text:
            children.append(Element(tag="text", attrs={
                "class": slot("center_text"),
                "x": _fmt(cx),
                "y": _fmt(cy),
                "font-size": str(center_font),
                "text-anchor": "middle",
                "dominant-baseline": "middle",
            }, children=(TextNode(center_text),)))

        svg_attrs: dict[str, Any] = {
            "class": slot("svg"),
            "viewBox": f"0 0 {side} {side}",
            "width": str(side),
            "height": str(side),
            "role": "img",
            "aria-label": _aria_summary(slices, is_donut),
        }
        svg = Element(tag="svg", attrs=svg_attrs, children=tuple(children))

        wrapper_children: list[Element] = [svg]
        if show_legend and len(slices) > 1:
            wrapper_children.append(
                _render_legend(slot, slices, palette)
            )

        return Element(
            tag=self._tag, attrs=wrapper_attrs,
            children=tuple(wrapper_children),
        )


# ───────────────────────────────────────────────────────────────────────
# Helpers
# ───────────────────────────────────────────────────────────────────────


def _coerce_slices(data: Any) -> list[tuple[str, float]]:
    if not data:
        return []
    out: list[tuple[str, float]] = []
    for item in data:
        if isinstance(item, (tuple, list)) and len(item) >= 2:
            try:
                value = float(item[1])
            except (TypeError, ValueError):
                continue
            # Negative / zero slices don't make a pie — skip silently.
            if value > 0:
                out.append((str(item[0]), value))
    return out


def _aria_summary(slices: list[tuple[str, float]], donut: bool) -> str:
    return text(
        "chart.summary",
        kind=text("chart.donut" if donut else "chart.pie"),
        what=text("chart.slices", n=len(slices)),
    )


def _render_legend(
    slot, slices: list[tuple[str, float]], palette: list[str],
) -> Element:
    """PieChart's static legend — the shared layer, fed from the palette
    (one colour per slice, cycling)."""
    return render_static_legend(
        slot,
        [(palette[i % len(palette)], str(label))
         for i, (label, _) in enumerate(slices)],
    )
