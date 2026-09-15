"""Default :class:`EmptyState` theme.

Centered column of : optional icon (large, muted) + title +
optional description + optional action slot. Used wherever a list,
table, filter result, or search returns nothing — gives the user
a clear "nothing here yet" signal instead of an awkward blank area.

Slots :
- ``root``        : the centering column
- ``icon``   : the icon wrapper (size + color)
- ``title``       : the heading text
- ``description`` : the muted supporting text
- ``actions``     : the action-button row at the bottom
"""

from __future__ import annotations

from typing import Any

EMPTY_STATE_THEME: dict[str, Any] = {
    "slots": {
        # Centred column ; ``py-12`` gives the empty space some
        # vertical presence so it doesn't look like a missing render.
        "root": (
            "flex flex-col items-center justify-center text-center "
            "gap-3 py-12 px-6 w-full"
        ),
        # The icon : circular background to set it apart from the page
        # chrome. Structural only — the colour tint follows ``color=``
        # and is applied in ``render`` (``muted`` keeps the soft look).
        # Size scales with the EmptyState's own ``size``.
        "icon": (
            "inline-flex items-center justify-center "
            "rounded-full mb-1"
        ),
        # Title : the "what's missing" headline. Stays neutral
        # colour ; the icon already carries the visual weight.
        "title": "font-semibold text-text",
        # Description : muted supporting copy. ``max-w-sm`` so long
        # descriptions wrap to a comfortable measure instead of
        # spanning a wide card.
        "description": "text-muted/80 max-w-sm leading-relaxed",
        # Action row : space above to separate it from the
        # description ; ``flex-wrap`` so multiple buttons line-break
        # on narrow widths instead of overflowing.
        "actions": "flex flex-wrap items-center justify-center gap-2 mt-2",
    },
    # Sizes scale the icon size + title text size. The standard 5
    # paliers ; default ``md`` is the sweet spot for in-card use.
    "sizes": {
        "xs": {
            "icon_box": "h-8 w-8",
            "icon_size": "sm",
            "title": "text-sm",
            "description": "text-xs",
        },
        "sm": {
            "icon_box": "h-10 w-10",
            "icon_size": "md",
            "title": "text-base",
            "description": "text-sm",
        },
        "md": {
            "icon_box": "h-14 w-14",
            "icon_size": "lg",
            "title": "text-lg",
            "description": "text-sm",
        },
        "lg": {
            "icon_box": "h-16 w-16",
            "icon_size": "xl",
            "title": "text-xl",
            "description": "text-base",
        },
        "xl": {
            "icon_box": "h-20 w-20",
            "icon_size": "2xl",
            "title": "text-2xl",
            "description": "text-base",
        },
    },
}
