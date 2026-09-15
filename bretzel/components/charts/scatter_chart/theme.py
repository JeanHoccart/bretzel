"""Default :class:`ScatterChart` theme.

Slot inventory :

- ``wrapper``    : outer ``<div>``, ``relative`` so the fixed-corner
  panel pattern carries over if a chart wants it (scatter v1 ships
  the floating tooltip, not the panel).
- ``svg``        : the chart SVG.
- ``dot``        : a single data point. Son ``fill`` est à ``70 %``
  pour que deux points superposés se voient — c'est l'intérêt d'un
  nuage. Le survol le rend PLEIN (``hover:fill-(--bz-solid)``).
- ``axis``       : axis line stroke + per-tick line strokes.
- ``axis_label`` : tick text fill + sizing.
- ``gridline``   : faint horizontal helpers behind the data.
- ``reference_line`` / ``reference_label`` : dashed threshold lines.
- ``legend`` / ``legend_item`` / ``legend_dot`` / ``legend_label``
  : multi-series legend (clickable toggle, same pattern as LineChart).
- ``empty``      : centered "no data" text.

``sizes`` per palier carries ``(h, dot_r, axis_font)``. Scatter dots
are slightly larger than line dots since they're the entire visual ;
no line to anchor on.
"""

from __future__ import annotations

from typing import Any

SCATTER_CHART_THEME: dict[str, Any] = {
    "slots": {
        "wrapper":      "relative flex flex-col gap-3 w-fit max-w-full",
        "svg":          "block max-w-full overflow-visible",
        # ``cursor-pointer`` because every dot is a hover target ; le
        # survol rend le point PLEIN, et c'est la seule façon de le
        # faire ici.
        #
        # ⚠️ Ce bloc a porté ``transition-opacity`` + ``hover:!opacity-100``
        # du 2026-06-?? au 2026-09-01, avec un commentaire annonçant un
        # « hover-pop effect ». Il n'y en avait aucun : la translucidité
        # du point est sur le ``fill`` (``/70``), pas sur ``opacity``, et
        # un point au repos rend ``opacity: 1`` (mesuré au navigateur).
        # ``hover:!opacity-100`` remettait donc à 1 une valeur déjà à 1,
        # et ``transition-opacity`` animait une propriété qui ne bouge
        # jamais. Deux classes qui décrivaient une intention au lieu de
        # la produire.
        #
        # ``transition-colors`` et pas ``transition-[fill]`` : la liste
        # de v4 couvre ``fill`` et ``stroke``, donc c'est un utilitaire
        # STANDARD là où la forme entre crochets est une variante
        # arbitraire — invisible en dev, cf. la memory
        # ``tailwind_browser_breaks_transitions``.
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
