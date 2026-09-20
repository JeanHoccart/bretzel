"""Default :class:`ScatterChart` theme.

Slot inventory :

- ``wrapper``    : outer ``<div>``, ``relative`` so the fixed-corner
  panel pattern carries over if a chart wants it (scatter v1 ships
  the floating tooltip, not the panel).
- ``svg``        : the chart SVG.
- ``dot``        : a single data point. Its ``fill`` is at ``70 %`` so
  two overlapping points are both visible — that is the point of a
  scatter. Hovering makes it SOLID (``hover:fill-(--bz-solid)``).
- ``axis``       : axis line stroke + per-tick line strokes.
- ``axis_label`` : tick text fill + sizing.
- ``gridline``   : faint horizontal helpers behind the data.
- ``reference_line`` / ``reference_label`` : dashed threshold lines.
- ``legend`` / ``legend_item`` / ``legend_dot`` / ``legend_label``
  : multi-series legend (clickable toggle, same pattern as LineChart).
- ``empty``      : centered "no data" text.

``sizes`` per step carries ``(h, dot_r, axis_font)``. Scatter dots
are slightly larger than line dots since they're the entire visual ;
no line to anchor on.
"""

from __future__ import annotations

from typing import Any

SCATTER_CHART_THEME: dict[str, Any] = {
    "slots": {
        "wrapper":      "relative flex flex-col gap-3 w-fit max-w-full",
        "svg":          "block max-w-full overflow-visible",
        # ``cursor-pointer`` because every dot is a hover target ; the
        # hover makes the point SOLID, and that is the only way to do it
        # here.
        #
        # ⚠️ This block carried ``transition-opacity`` +
        # ``hover:!opacity-100`` from 2026-06-?? to 2026-09-01, with a
        # comment announcing a "hover-pop effect". There was none: the
        # point's translucency is on the ``fill`` (``/70``), not on
        # ``opacity``, and a point at rest renders ``opacity: 1``
        # (measured in the browser). ``hover:!opacity-100`` therefore put
        # back to 1 a value already at 1, and ``transition-opacity``
        # animated a property that never moves. Two classes that
        # described an intent instead of producing it.
        #
        # ``transition-colors`` and not ``transition-[fill]``: v4's list
        # covers ``fill`` and ``stroke``, so it is a STANDARD utility
        # where the bracketed form is an arbitrary variant — invisible in
        # dev, cf. the memory ``tailwind_browser_breaks_transitions``.
        "dot": (
            "fill-(--bz-solid)/70 cursor-pointer "
            "transition-colors duration-150 ease-out "
            "hover:fill-(--bz-solid)"
        ),
        "axis":         "stroke-text/30",
        "axis_label":   "fill-text/60",
        "gridline":     "stroke-text/10",
        "reference_line":  "stroke-(--bz-solid)/60",
        "reference_label": "fill-(--bz-solid)/80 font-medium",
        "legend":       "flex flex-wrap items-center justify-center gap-x-4 gap-y-1",
        "legend_item": (
            "flex items-center gap-2 cursor-pointer "
            "transition-opacity duration-150 "
            "outline-none focus-visible:ring-2 focus-visible:ring-text/30 "
            "rounded px-1"
        ),
        "legend_dot":   "size-3 rounded-selector shrink-0 bg-(--bz-solid)",
        "legend_label": "text-xs text-text/70",
        "empty":        "fill-text/40 text-sm",
    },
    "sizes": {
        # name → {height, dot_radius, axis_font}
        "xs": {"h": 140, "dot": 3.0, "axis": 10},
        "sm": {"h": 200, "dot": 3.5, "axis": 11},
        "md": {"h": 280, "dot": 4.0, "axis": 12},
        "lg": {"h": 360, "dot": 4.5, "axis": 13},
        "xl": {"h": 440, "dot": 5.0, "axis": 14},
    },
    "palette": ("primary", "success", "warning", "info", "error", "muted"),
}
