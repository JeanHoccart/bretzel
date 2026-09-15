"""Default :class:`Skeleton` theme.

Loading-placeholder block — pulses to suggest "content is on its
way". Three shapes : text line, circle (avatar placeholder), or
arbitrary rectangle.

Slots :
- ``root`` : the placeholder itself
"""

from __future__ import annotations

from typing import Any

SKELETON_THEME: dict[str, Any] = {
    "slots": {
        # Default rectangular shape ; ``animate-pulse`` is Tailwind's
        # built-in subtle fade. ``bg-muted/30`` is light enough to
        # work on both interface + background surfaces.
        "root": "block bg-muted/30",
    },
    # Each variant bakes a sensible default dimension so the skeleton
    # is visible without the user having to pass ``width=`` /
    # ``height=`` for the common case. Explicit width/height land as
    # inline styles and override (inline > CSS class specificity).
    "variants": {
        # Line of body text — typical paragraph line height.
        "text":      "rounded h-4 w-full",
        # Avatar placeholder — matches Avatar's ``md`` size.
        "circle":    "rounded-full h-10 w-10",
        # Generic content chunk — card thumbnail / image / chart.
        "rectangle": "rounded-box h-20 w-full",
    },
}
