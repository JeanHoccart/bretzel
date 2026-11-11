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

A ``None`` y is a HOLE, as on ``ui.line_chart`` : the line stops and
starts again, a point alone between two holes is a dot, and the last
dot (``show_last_dot``) is only drawn when the last point has a value.

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
from bretzel.components.base.theme_values import theme_context
from bretzel.components.charts._svg import (
    _fmt,
    area_path,
    line_path,
    linear_scale,
    smooth_path,
)
from bretzel.components.charts.series import bad_point, gap_y, runs_between_holes
from bretzel.components.charts.sparkline.theme import SPARKLINE_THEME
from bretzel.core.tree import Element
from bretzel.render import text


def _coerce_points(data: Any) -> list[tuple[float, float | None]]:
    """Normalise ``data=`` into a list of ``(x, y)`` floats, ``y`` None
    for a hole.

    Accepts ``list[number]`` (x = index) or ``list[(x, y)]``. A point that
    is neither raises — the other charts do too: a dropped point bent the
    trend without a word.
    """
    if not data:
        return []
    points: list[tuple[float, float | None]] = []
    for i, item in enumerate(data):
        try:
            if isinstance(item, (tuple, list)) and len(item) == 2:
                points.append((float(item[0]), gap_y(item[1])))
            elif not isinstance(item, (tuple, list, dict, str)):
                points.append((float(i), gap_y(item)))
            else:
                raise bad_point("Sparkline", item,
                                "a number, or an (x, y) pair (None for a hole)")
        except (TypeError, ValueError):
            raise bad_point("Sparkline", item,
                            "a number, or an (x, y) pair (None for a hole)") from None
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
        # Direct forward: the base layer drops reactive None kwargs (keeps the default).
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

        known = [y for _, y in points if y is not None]
        if not known:
            return Element(tag=self._tag, attrs=attrs, children=())

        xs = [x for x, _ in points]
        xmin, xmax = min(xs), max(xs)
        ymin, ymax = min(known), max(known)

        pad = stroke_w
        x_scale = linear_scale(xmin, xmax, pad, width - pad)
        # Flip y so larger values render higher on screen.
        y_scale = linear_scale(ymin, ymax, height - pad, pad)
        # One run per stretch between two holes (cf. ``ui.line_chart``).
        runs = [[(x_scale(x), y_scale(y)) for x, y in run]
                for run in runs_between_holes(points)]
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
                            "class": self.compose_class("area_gradient_color"),
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
                    "class": self.compose_class("area"),
                    "fill": f"url(#{gradient_id})",
                    "d": "".join(area_path(run, baseline_y=baseline_y, smooth=smooth)
                                 for run in runs if len(run) > 1),
                },
                children=(),
            ))

        children_list.append(Element(
            tag="path",
            attrs={
                "class": self.compose_class("line"),
                "d": "".join(smooth_path(run) if smooth else line_path(run)
                             for run in runs if len(run) > 1),
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

        # A point alone between two holes has no segment : it is a dot.
        dots = [run[0] for run in runs if len(run) == 1]
        # The last dot says « where it is now » : not when the series
        # ends on a hole.
        if show_last_dot and points[-1][1] is not None and runs[-1][-1] not in dots:
            dots.append(runs[-1][-1])
        for last_x, last_y in dots:
            children_list.append(Element(
                tag="circle",
                attrs={
                    "class": self.compose_class("dot"),
                    "cx": _fmt(last_x),
                    "cy": _fmt(last_y),
                    "r": str(dot_r),
                },
                children=(),
            ))

        return Element(tag=self._tag, attrs=attrs, children=tuple(children_list))


def _aria_summary(points: list[tuple[float, float | None]]) -> str:
    known = [y for _, y in points if y is not None]
    if not known:
        return text("chart.sparkline_empty")
    ymin, ymax = min(known), max(known)
    return text(
        "chart.sparkline_summary",
        n=len(known),
        low=f"{round(ymin, 2):g}",
        high=f"{round(ymax, 2):g}",
    )
