"""``Sparkline`` — inline single-series trend indicator.

Designed for KPI cards and dense table rows. Renders a server-side
SVG polyline with optional area fill and a terminal dot ; no axes, no
labels, no legend. The whole point of a sparkline is to **read at a
glance** the shape of a series next to its headline number.

Data shape :

- ``list[number]`` — x = index, y = value. The common case.
- ``list[tuple[x, y]]`` — explicit x ; the chart still scales linearly
  across the index range, but tuple form keeps a future ``time`` axis
  option open without changing the API.

A11y : the SVG carries ``role="img"`` and an auto-generated
``aria-label`` summarising the trend (``"Sparkline — 12 points, min 4,
max 21"``). Apps can override via ``aria_label=`` on the kwargs.
``BINDABLE_PROPS = ()`` — data updates flow through a server refresh
(``@refreshable``) which Bretzel's idiomorph diff handles
gracefully for an SVG of this size.
"""

from __future__ import annotations

from typing import Any, ClassVar

from bretzel.components.base import Component, reactive_prop
from bretzel.components.base._wiring import theme_context
from bretzel.components.charts._svg import (
    _fmt,
    area_path,
    line_path,
    linear_scale,
    smooth_path,
)
from bretzel.components.charts.sparkline.theme import SPARKLINE_THEME
from bretzel.core.tree import Element
from bretzel.render import text


def _coerce_points(data: Any) -> list[tuple[float, float]]:
    """Normalise ``data=`` into a list of ``(x, y)`` floats.

    Accepts ``list[number]`` (x = index) or ``list[tuple]``. Invalid
    entries are silently dropped — an empty result triggers the empty
    state instead of raising mid-render.
    """
    if not data:
        return []
    points: list[tuple[float, float]] = []
    for i, item in enumerate(data):
        if isinstance(item, (tuple, list)) and len(item) >= 2:
            try:
                points.append((float(item[0]), float(item[1])))
            except (TypeError, ValueError):
                continue
        else:
            try:
                points.append((float(i), float(item)))
            except (TypeError, ValueError):
                continue
    return points


class Sparkline(Component):
    """Inline single-series trend indicator."""

    THEME: ClassVar[dict[str, Any]] = SPARKLINE_THEME
    THEME_KEY: ClassVar[str] = "sparkline"
    DEFAULT_TAG: ClassVar[str] = "svg"
    IS_CONTAINER: ClassVar[bool] = False
    # Data updates go through ``@refreshable`` ; no client-side
    # binding surface for v1. A future v2 may bind ``data=`` when a
    # live-streaming use case appears.
    BINDABLE_PROPS: ClassVar[tuple[str, ...]] = ()

    color: str = reactive_prop(default="primary", emit_attr=False)
    size: str = reactive_prop(default="sm", emit_attr=False)
    smooth: bool = reactive_prop(default=False, emit_attr=False)
    area_fill: bool = reactive_prop(default=False, emit_attr=False)
    show_last_dot: bool = reactive_prop(default=False, emit_attr=False)
    width: int = reactive_prop(default=120, emit_attr=False)

    def __init__(
        self,
        data: Any = None,
        *,
        color: str | None = None,
        size: str | None = None,
        smooth: bool | None = None,
        area_fill: bool | None = None,
        show_last_dot: bool | None = None,
        width: int | None = None,
        **kwargs: Any,
    ) -> None:
        # ``data`` is positional, not a reactive_prop — sparkline payloads
        # are server-resolved lists, not bindable scalars. Stash it on
        # the instance so ``render()`` can read it.
        self._data = data or []
        # Forward direct : le socle drope les kwargs reactive None (garde le defaut).
        super().__init__(
            color=color, size=size, smooth=smooth,
            area_fill=area_fill, show_last_dot=show_last_dot,
            width=width,
            **kwargs,
        )

    def render(self) -> Element:
        theme, _slots, sizes, size_name, _color = theme_context(self, size_default="sm")

        smooth = bool(self._reactive_values.get("smooth"))
        area_fill = bool(self._reactive_values.get("area_fill"))
        show_last_dot = bool(self._reactive_values.get("show_last_dot"))
        width = int(self._reactive_values.get("width") or 120)

        size_tuple = sizes.get(size_name) or sizes.get("sm") or (24, 1.25, 2.0)
        height, stroke_w, dot_r = size_tuple

        points = _coerce_points(self._data)

        attrs = self.emit_attrs()
        attrs["class"] = self.compose_class(
            "root", apply_variant_size_modifiers=False
        )
        attrs.setdefault("role", "img")
        attrs["viewBox"] = f"0 0 {width} {height}"
        attrs["width"] = str(width)
        attrs["height"] = str(height)
        attrs["preserveAspectRatio"] = "none"
        if "aria-label" not in attrs:
            attrs["aria-label"] = _aria_summary(points)

        if not points:
            return Element(tag=self._tag, attrs=attrs, children=())

        # Single-pass min/max — folded so dense series only walk once.
        xmin = xmax = points[0][0]
        ymin = ymax = points[0][1]
        for x, y in points:
            if x < xmin:
                xmin = x
            elif x > xmax:
                xmax = x
            if y < ymin:
                ymin = y
            elif y > ymax:
                ymax = y

        pad = stroke_w
        x_scale = linear_scale(xmin, xmax, pad, width - pad)
        # Flip y so larger values render higher on screen.
        y_scale = linear_scale(ymin, ymax, height - pad, pad)
        scaled = [(x_scale(x), y_scale(y)) for x, y in points]
        baseline_y = height - pad

        children_list: list = []

        # Gradient ``<defs>`` for the optional area fill — same
        # ``currentColor`` trick as LineChart : the ``area`` slot
        # provides ``text-{color}`` so the stops resolve to the
        # sparkline's semantic colour without baking a hex in.
        gradient_id = f"{self.id}-area-grad"
        if area_fill:
            grad = theme.get("area_gradient",
                             {"top": 0.40, "bottom": 0.08})
            children_list.append(Element(
                tag="defs", attrs={}, children=(
                    Element(
                        tag="linearGradient",
                        attrs={
                            "id": gradient_id,
                            # Colour class on the gradient itself :
                            # ``<stop currentColor>`` inherits from
                            # its parent, not from the painted path.
                            "class": self.compose_class(
                                "area_gradient_color",
                                apply_variant_size_modifiers=False,
                            ),
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
                    ),
                ),
            ))
            children_list.append(Element(
                tag="path",
                attrs={
                    "class": self.compose_class(
                        "area",
                        apply_variant_size_modifiers=False,
                    ),
                    "fill": f"url(#{gradient_id})",
                    "d": area_path(scaled, baseline_y=baseline_y,
                                   smooth=smooth),
                },
                children=(),
            ))

        children_list.append(Element(
            tag="path",
            attrs={
                "class": self.compose_class(
                    "line",
                    apply_variant_size_modifiers=False,
                ),
                "d": smooth_path(scaled) if smooth else line_path(scaled),
                "stroke-width": str(stroke_w),
                "stroke-linecap": "round",
                "stroke-linejoin": "round",
                # ``pathLength="1"`` normalises the entry-draw
                # ``stroke-dasharray`` so the reveal animation runs
                # for the full duration regardless of how short the
                # sparkline's polyline is.
                "pathLength": "1",
            },
            children=(),
        ))

        if show_last_dot:
            last_x, last_y = scaled[-1]
            children_list.append(Element(
                tag="circle",
                attrs={
                    "class": self.compose_class(
                        "dot",
                        apply_variant_size_modifiers=False,
                    ),
                    "cx": _fmt(last_x),
                    "cy": _fmt(last_y),
                    "r": str(dot_r),
                },
                children=(),
            ))

        return Element(tag=self._tag, attrs=attrs, children=tuple(children_list))


def _aria_summary(points: list[tuple[float, float]]) -> str:
    if not points:
        return text("chart.sparkline_empty")
    ymin = ymax = points[0][1]
    for _, y in points:
        if y < ymin:
            ymin = y
        elif y > ymax:
            ymax = y
    return text(
        "chart.sparkline_summary",
        n=len(points),
        low=f"{round(ymin, 2):g}",
        high=f"{round(ymax, 2):g}",
    )
