"""Default :class:`Heading` theme.

``font-sans tracking-tight``, ``font-bold`` default. Level/size decoupling :
the HTML tag drives SEO semantics, the visible size is independent — it
auto-derives from the level (``level_sizes``) or is set explicitly. Apps
shift the visual scale globally by passing a different ``HEADING_THEME`` at
``Bretzel(theme=…)`` build time.
"""

from __future__ import annotations

from typing import Any

HEADING_THEME: dict[str, Any] = {
    "slots": {
        "root": "font-sans tracking-tight",
    },
    "sizes": {
        "xs": "text-xs",
        "sm": "text-sm",
        "md": "text-base",
        "lg": "text-lg",
        "xl": "text-xl",
        "2xl": "text-2xl",
        "3xl": "text-3xl",
        "4xl": "text-4xl lg:text-5xl",
        "5xl": "text-5xl lg:text-6xl",
        "6xl": "text-6xl lg:text-7xl",
        "7xl": "text-7xl lg:text-8xl",
        "8xl": "text-8xl lg:text-9xl",
    },
    "weights": {
        "normal": "font-normal",
        "medium": "font-medium",
        "semibold": "font-semibold",
        "bold": "font-bold",
        "extrabold": "font-extrabold",
    },
    # Auto-pick a size when ``size=`` isn't passed : level 1 reads
    # large by default, level 6 reads inline-paragraph size. Override
    # by passing ``size=`` explicitly.
    "level_sizes": {
        1: "4xl",
        2: "3xl",
        3: "2xl",
        4: "xl",
        5: "lg",
        6: "md",
    },
}
