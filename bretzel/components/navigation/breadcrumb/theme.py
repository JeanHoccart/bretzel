"""Default :class:`Breadcrumb` theme.

A flat row of links separated by a chevron (or a custom marker).
The last item is rendered as plain text (current location, no link)
and gets a slightly stronger color to read as the "you are here"
landmark.

Slots :
- ``root``      : the ``<nav>`` flex row
- ``item``      : the clickable parents
- ``current``   : the last segment (rendered as ``<span>``)
- ``separator`` : the chevron / slash between items
"""

from __future__ import annotations

from typing import Any

BREADCRUMB_THEME: dict[str, Any] = {
    "slots": {
        "root": "flex items-center gap-1.5 leading-none",
        # Items stay muted at rest (universal "non-active link" grey),
        # tinted to ``color=`` on hover. The focus ring picks up the
        # same color for consistency.
        "item": (
            "inline-flex items-center gap-1.5 text-muted "
            "max-w-[12rem] truncate "
            "transition-colors duration-150 hover:text-(--bz-text) "
            "focus-visible:outline-none focus-visible:ring-2 "
            "focus-visible:ring-(--bz-focus) focus-visible:ring-offset-2 "
            "focus-visible:ring-offset-background rounded-selector"
        ),
        # Current segment ("you are here") tinted to ``color=`` so
        # the breadcrumb's trail accent matches the page / section
        # palette. Bold weight already makes it stand out as the
        # landmark ; the colour is the secondary signal.
        "current": (
            "inline-flex items-center gap-1.5 "
            "text-(--bz-text) font-medium"
        ),
        "separator": "text-muted/50 shrink-0",
    },
    "sizes": {
        "xs": "text-[10px]",
        "sm": "text-xs",
        "md": "text-sm",
        "lg": "text-base",
        "xl": "text-lg",
    },
}
