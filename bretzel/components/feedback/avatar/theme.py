"""Default :class:`Avatar` theme.

Round (or square) image / initials chip with an optional status dot
overlaid in the bottom-right corner.

Slots :
- ``root``    : ``relative inline-flex`` wrapper that hosts the image
                / initials and the status dot
- ``image``   : the ``<img>`` tag (covers root)
- ``initials``: fallback ``<span>`` with the user's initials
- ``status``  : tiny status dot (online / busy / etc.)
"""

from __future__ import annotations

from typing import Any

AVATAR_THEME: dict[str, Any] = {
    "slots": {
        # ``relative`` positions the status dot. ``overflow-hidden`` is
        # INTENTIONALLY off so the dot's ring can extend outside the box —
        # the image clips itself via its own ``rounded-{shape}`` class.
        "root": (
            "relative inline-flex items-center justify-center "
            "shrink-0 select-none "
            "bg-(--bz-bg) text-(--bz-text) font-medium"
        ),
        # Image carries ``rounded-{shape}`` (render-time) so it clips itself.
        "image": "h-full w-full object-cover",
        "initials": "leading-none tracking-tight",
        # Outlined status dot — the ring keeps it readable on any colour.
        "status": (
            "absolute bottom-0 right-0 rounded-full "
            "ring-2 ring-background"
        ),
    },
    "shapes": {
        "circle": "rounded-full",
        "square": "rounded-selector",
    },
    "sizes": {
        "xs":  {"root": "h-6 w-6 text-[10px]",   "status": "h-1.5 w-1.5"},
        "sm":  {"root": "h-8 w-8 text-xs",       "status": "h-2 w-2"},
        "md":  {"root": "h-10 w-10 text-sm",     "status": "h-2.5 w-2.5"},
        "lg":  {"root": "h-12 w-12 text-base",   "status": "h-3 w-3"},
        "xl":  {"root": "h-16 w-16 text-lg",     "status": "h-3.5 w-3.5"},
        "2xl": {"root": "h-20 w-20 text-xl",     "status": "h-4 w-4"},
    },
    # The status dot color comes from the semantic theme palette.
    # ``away`` = warning yellow, ``busy`` = error red, etc.
    "statuses": {
        "online":  "bg-success",
        "offline": "bg-muted",
        "busy":    "bg-error",
        "away":    "bg-warning",
    },
}
