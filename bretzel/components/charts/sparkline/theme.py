"""Default :class:`Sparkline` theme.

Slots — ``root`` (SVG wrapper), ``line`` (polyline stroke), ``area``
(optional area-fill watermark), ``dot`` (terminal marker).

``sizes`` is a 3-tuple per palier — ``(height_px, stroke_width,
dot_radius)``. The chart width follows the ``width=`` kwarg ; only
the height is theme-driven, so the silhouette scales harmonically
with stroke and dot dimensions.
"""

from __future__ import annotations

from typing import Any

SPARKLINE_THEME: dict[str, Any] = {
    "slots": {
        "root": "inline-block align-text-bottom overflow-visible",
        # ``transition-[d]`` morphs the silhouette on data refresh.
        # ``bz-line-entry`` reveals the stroke on first paint.
        # Sparklines skip ``drop-shadow`` — they're inline-tiny and
        # any shadow reads as fuzz at this scale.
        "line": (
            "stroke-(--bz-solid) fill-none "
            "transition-[d] duration-500 ease-out "
            "bz-line-entry"
        ),
        # The gradient's colour lives on the ``<linearGradient>``
        # element via the ``area_gradient_color`` slot below — SVG
        # ``<stop>`` elements inherit ``currentColor`` from their
        # tree ancestor, not from the element painting the gradient.
        # The area path itself stays bare ; the fill comes from
        # ``fill="url(#...)"``.
        "area": "",
        # ``color`` on the ``<linearGradient>`` resolves the stops'
        # ``stop-color: currentColor`` to the sparkline's palette
        # colour. ``--bz-solid`` comes from the component's bridge.
        "area_gradient_color": "text-(--bz-text)",
        "dot":  "fill-(--bz-solid)",
    },
    "sizes": {
        "xs": (16,  1.0,  1.5),
        "sm": (24,  1.25, 2.0),
        "md": (32,  1.5,  2.5),
        "lg": (48,  1.75, 3.0),
        "xl": (64,  2.0,  3.5),
    },
    # Gradient stop opacities for the area fill — top (just under the
    # silhouette) and bottom. Bottom is non-zero so the fill stays
    # the sparkline's colour throughout instead of fading to the
    # surrounding page bg (which reads as "dark" on a dark theme).
    "area_gradient": {"top": 0.40, "bottom": 0.08},
}
