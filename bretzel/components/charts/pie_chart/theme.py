"""Default :class:`PieChart` theme.

Slot inventory :

- ``wrapper``     : outer ``<div>`` hosting the SVG and the legend.
- ``svg``         : the chart SVG.
- ``slice``       : a single wedge path — colour cycled per item.
- ``slice_label``: optional in-chart text for the arc value / percent.
- ``center_text`` : optional centred text for donut mode (total, KPI).
- ``legend``      : legend row container.
- ``legend_dot``  : the colour swatch.
- ``legend_label``: legend text.
- ``empty``       : centered "no data" text when the payload is empty.

``sizes`` per palier carries ``{h, label, center}`` — the
chart itself is a square of side ``h``. Donut inner radius is a
fraction of the outer (kept as a constant ; v1 keeps the API tight).

``palette`` is the auto-cycle ; pies almost always pass colours
explicitly so the order is meaningful (often a brand palette), but
the default is the same six-colour semantic ramp every other chart
uses.
"""

from __future__ import annotations

from typing import Any

PIE_CHART_THEME: dict[str, Any] = {
    "slots": {
        "wrapper":      "flex flex-col gap-3 items-center",
        # ``group/pie`` enables the slice ``group-hover/pie:opacity-80``
        # dim-others polish (the hovered slice keeps full opacity via
        # ``hover:!opacity-100`` on its own class).
        "svg":          "block overflow-visible group/pie",
        # ``transition-[d,opacity]`` morphs the wedge on data
        # refresh and powers the hover dim-others polish below.
        # ``bz-slice-entry`` runs once on first paint — wedges scale
        # in from the chart centre (CSS keyframe in
        # ``render/shell.py``).
        "slice": (
            "fill-(--bz-solid) stroke-background "
            "transition-[d,opacity] duration-400 ease-out "
            "bz-slice-entry"
        ),
        "slice_label":  "fill-text font-medium",
        "center_text":  "fill-text font-semibold",
        "legend":       "flex flex-wrap items-center justify-center gap-x-4 gap-y-1",
        "legend_dot":   "size-3 rounded-selector shrink-0 bg-(--bz-solid)",
        "legend_label": "text-xs text-text/70",
        "empty":        "fill-text/40 text-sm",
    },
    "sizes": {
        # name → {h, label, center}
        "xs": {"h": 140, "label": 10, "center": 14},
        "sm": {"h": 200, "label": 11, "center": 18},
        "md": {"h": 280, "label": 12, "center": 22},
        "lg": {"h": 360, "label": 13, "center": 28},
        "xl": {"h": 440, "label": 14, "center": 34},
    },
    "palette": ("primary", "success", "warning", "info", "error", "muted"),
}
