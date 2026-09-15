"""Default :class:`BarChart` theme.

Slot inventory :

- ``wrapper``    : outer ``<div>`` hosting the SVG and the legend.
- ``svg``        : the chart SVG itself.
- ``bar``        : bar fill — le palier ``--bz-solid``, posé par série
                   (chaque série reçoit son propre pont).
- ``axis``       : axis line stroke + the tick line strokes.
- ``axis_label`` : tick text fill + sizing.
- ``gridline``   : faint horizontal helpers behind the bars.
- ``value_label``: optional in-chart number above each bar.
- ``segment_label``: the percentage inside a ``stacked_100`` segment
  (contrasts against the segment fill, unlike ``value_label``).
- ``legend``     : legend row container (HTML, not SVG — text wraps nicely).
- ``legend_dot`` : the colour swatch next to each series name.
- ``legend_label``: legend text fill + sizing.
- ``empty``      : centered "no data" text when the series is empty.

``sizes`` is a dict per palier — height + axis font + bar padding ratio.
``palette`` is the auto-cycle for multi-series when no per-series color
is set.
"""

from __future__ import annotations

from typing import Any

BAR_CHART_THEME: dict[str, Any] = {
    "slots": {
        "wrapper":      "flex flex-col gap-3",
        "svg":          "block w-full overflow-visible",
        # ``transition-[y,height,opacity]`` morphs the bar on data
        # refresh (grow / shrink smoothly). ``bz-bar-entry`` runs
        # once on first paint and scales the bar up from its
        # baseline (CSS keyframe in ``render/shell.py``).
        "bar": (
            "fill-(--bz-solid) "
            "transition-[y,height,opacity] duration-400 ease-out "
            "bz-bar-entry"
        ),
        "axis":         "stroke-text/30",
        "axis_label":   "fill-text/60",
        "gridline":     "stroke-text/10",
        # Reference lines — same recipe as LineChart's theme : the
        # Le pont de la référence porte sa couleur, so
        # ``Reference(color="success")`` paints a green threshold
        # while a bare ``Reference(value=...)`` falls back to muted.
        "reference_line":  "stroke-(--bz-solid)/60",
        "reference_label": "fill-(--bz-solid)/80 font-medium",
        "value_label":  "fill-text font-medium",
        # Étiquette posée DANS un segment coloré (variant stacked_100),
        # pas au-dessus d'une barre : elle doit contraster avec le
        # remplissage, d'où ``--bz-on-solid`` (la couleur de premier plan de
        # la teinte du segment) là où ``value_label`` utilise la couleur
        # de texte de la page. ``pointer-events-none`` pour ne pas voler
        # le survol au rect qui porte le tooltip.
        "segment_label": (
            "fill-(--bz-on-solid) font-medium pointer-events-none "
            "select-none"
        ),
        "legend":       "flex flex-wrap items-center justify-center gap-x-4 gap-y-1",
        "legend_dot":   "size-3 rounded-selector shrink-0 bg-(--bz-solid)",
        "legend_label": "text-xs text-text/70",
        "empty":        "fill-text/40 text-sm",
    },
    "sizes": {
        # name → {height_px, axis_font_px, bar_padding_ratio, value_font_px}
        "xs": {"h": 140, "axis": 10, "pad": 0.25, "value": 10},
        "sm": {"h": 200, "axis": 11, "pad": 0.20, "value": 10},
        "md": {"h": 280, "axis": 12, "pad": 0.20, "value": 11},
        "lg": {"h": 360, "axis": 13, "pad": 0.18, "value": 12},
        "xl": {"h": 440, "axis": 14, "pad": 0.15, "value": 13},
    },
    # Auto-cycle colours when a multi-series payload omits per-Series colours.
    "palette": ("primary", "success", "warning", "info", "error", "muted"),
}
