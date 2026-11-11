"""Default :class:`Avatar` theme.

Round (or square) image / initials chip with an optional status dot
overlaid in the bottom-right corner.

Slots :
- ``root``    : ``relative inline-flex`` wrapper that hosts the image
                / initials and the status dot
- ``image``   : the ``<img>`` tag (covers root)
- ``initials``: fallback ``<span>`` with the user's initials
- ``status``  : tiny status dot (online / busy / etc.)

Variants :

- ``soft`` (default): a 10 % tint and the colour as ink. Right for a
  list of people on a page, where the disc must not out-shout the name
  beside it.
- ``solid``: the full colour and its derived foreground. For a disc
  that IS the information — a card's owner on a board — and for dark
  surfaces, where the 10 % tint lands within 1.1:1 of the card it sits
  on and the disc disappears.
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
            "shrink-0 select-none font-medium"
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
    "variants": {
        "soft": "bg-(--bz-bg) text-(--bz-text)",
        "solid": "bg-(--bz-solid) text-(--bz-on-solid)",
    },
    "shapes": {
        "circle": "rounded-full",
        "square": "rounded-selector",
    },
    # ``xs`` is ``h-7``, not ``h-6``: ``text-xs`` is the smallest text
    # step, so the disc is what must leave room for two initials. At
    # 3 px per step (a density an app can choose) ``h-6`` is 18 px, and
    # "SD" overflowed it.
    "sizes": {
        "xs":  {"root": "h-7 w-7 text-xs",   "status": "h-1.5 w-1.5"},
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
