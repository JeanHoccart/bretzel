"""Default :class:`ScatterChart` theme.

Slot inventory :

- ``wrapper``    : outer ``<div>``, ``relative`` so the fixed-corner
  panel pattern carries over if a chart wants it (scatter ships
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
        # Fills its container: the plot is drawn in percentages of it
        # (``_svg.PLOT_SPAN``) — same reason as LineChart's wrapper.
        # The focus ring: the chart is one tab stop (``keyboard_attrs``).
        "wrapper":      "relative flex flex-col gap-3 w-full min-w-0 rounded outline-none focus-visible:ring-2 focus-visible:ring-text/30",
        "svg":          "block overflow-visible",
        # ``cursor-pointer`` because every dot is a hover target ; the
        # hover makes the point SOLID, and that is the only way to do it
        # here.
        #
        # ⚠️ No ``transition-opacity`` or ``hover:!opacity-100`` here: the
        # point's translucency is on the ``fill`` (``/70``), not on
        # ``opacity``, and a point at rest renders ``opacity: 1``.
        # ``hover:!opacity-100`` would put back to 1 a value already at 1,
        # and ``transition-opacity`` would animate a property that never
        # moves.
        #
        # ``transition-colors`` and not ``transition-[fill]``: v4's list
        # covers ``fill`` and ``stroke``, so it is a STANDARD utility
        # where the bracketed form is an arbitrary variant — invisible in
        # dev.
        "dot": (
            "fill-(--bz-solid)/70 cursor-pointer "
            "transition-colors duration-150 ease-out "
            "hover:fill-(--bz-solid)"
        ),
        "axis":         "stroke-text/30",
        "axis_label":   "fill-text/60",
        # The axis titles, level: the vertical axis's above the plot at
        # its left, the horizontal axis's below it at its right.
        "title_top":    "self-start text-text/60",
        "title_bottom": "self-end text-text/60",
        "gridline":     "stroke-text/10",
        "reference_line":  "stroke-(--bz-border-hover)",
        # Painted OVER the dots: a halo in the page colour keeps it
        # readable, and it gives the hover back to the dots beneath.
        "reference_label": (
            "fill-(--bz-text) font-medium pointer-events-none "
            "stroke-background stroke-3 [paint-order:stroke]"
        ),
        "legend":       "flex flex-wrap items-center justify-center gap-x-4 gap-y-1",
        "legend_item": (
            "flex items-center gap-2 cursor-pointer "
            "transition-opacity duration-150 "
            "outline-none focus-visible:ring-2 focus-visible:ring-text/30 "
            "rounded px-1"
        ),
        "legend_dot":   "size-3 rounded-selector shrink-0 bg-(--bz-solid)",
        "legend_label": "text-xs text-text/70",
        # « Voir les données »: the ``<details>`` and its summary
        # (``data_table``); the table inside is a ``ui.table``.
        "data":         "group w-full",
        "data_toggle":  (
            "w-fit cursor-pointer select-none text-text/60 "
            "hover:text-text rounded outline-none "
            "focus-visible:ring-2 focus-visible:ring-text/30"
        ),
        "empty":        "fill-text/40 text-sm",
    },
    "sizes": {
        # name → {height, dot_radius, axis_font}
        # + the font of the HTML around the plot — axis titles, « Voir les
        # données » — on the axis labels' step (``titled``, ``data_table``).
        "xs": {"h": 140, "dot_radius": 3.0, "axis_font": 10, "title_top": "text-xs", "title_bottom": "text-xs", "data_toggle": "text-xs"},
        "sm": {"h": 200, "dot_radius": 3.5, "axis_font": 11, "title_top": "text-xs", "title_bottom": "text-xs", "data_toggle": "text-xs"},
        "md": {"h": 280, "dot_radius": 4.0, "axis_font": 12, "title_top": "text-xs", "title_bottom": "text-xs", "data_toggle": "text-xs"},
        "lg": {"h": 360, "dot_radius": 4.5, "axis_font": 13, "title_top": "text-sm", "title_bottom": "text-sm", "data_toggle": "text-sm"},
        "xl": {"h": 440, "dot_radius": 5.0, "axis_font": 14, "title_top": "text-sm", "title_bottom": "text-sm", "data_toggle": "text-sm"},
    },
    # The auto-cycle when a series carries no ``color=``. BRAND colours
    # first, then status colours, ``error`` last. The identity's author
    # chose ``primary`` and ``secondary`` as a pair, so they are the two
    # the framework can trust to differ; a status colour is only
    # guaranteed to differ from the OTHER status colours
    # (``test_palette_distinctness``), not from an arbitrary primary. The
    # old cycle went primary → success, so under a green identity the
    # first two series came out the same green. ``info`` next, the only
    # status colour that says nothing; ``error`` last, since a series in
    # red reads as an alarm.
    "palette": (
        "primary", "secondary", "info", "success", "warning", "error",
        "muted",
    ),
}
