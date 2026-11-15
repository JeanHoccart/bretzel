"""Default :class:`Divider` theme.

The line is the framework's border, and nothing else: its colour is
``border-text/10`` for the neutral ``muted`` — the same line as the
sidebar's edge or a card's outline — and the colour's resting border step
(``--bz-border``) for any other ``color=``; its width is the theme's
``--bz-stroke``, like every border. A line in the muted TEXT colour,
even at 20 %, has about three times the contrast of those borders, and
next to a sidebar's edge it reads as a thicker line.

⚠️ At 125 and 150 % a 1 px line covers 1.25 or 1.5 device pixels, so it
is drawn over two rows, one of them partly — a box and a border alike
(measured, Chromium 147: same pixels for both). No CSS makes it a single
device row there; what the divider can do is look exactly like the
borders, which it now does.

The optional centred label: uppercase + tracking-widest + ``text-xs``, in
the colour's text step.

Slots :
- ``root``         : the flex container, orientation-aware
- ``line``         : the rule ; takes the bulk of the space via ``grow``
- ``line_neutral`` : its colour when ``color="muted"`` (the default)
- ``line_tinted``  : its colour for any other ``color=``
- ``label``        : optional, sandwiched between two ``line`` instances

``gap=`` — the space on each side of the line, across it (above and below
a horizontal one), the word and the steps of the other ``gap`` (a flex
container's, ``ui.resizable``'s), so the same tokens (``--bz-gap-*``).
``sm`` (the default) is the space it always had, 8 px; ``none`` draws the
line flush — the lines of a mail's header, between fields that carry their
own height.
"""

from __future__ import annotations

from typing import Any

DIVIDER_THEME: dict[str, Any] = {
    "slots": {
        "root": "flex items-center justify-center",
        "line": "grow",
        "line_neutral": "border-line",
        "line_tinted": "border-(--bz-border)",
        "label": (
            "text-xs font-semibold px-4 whitespace-nowrap "
            "tracking-widest uppercase"
        ),
    },
    #: The space around the line, by ``gap=`` step and orientation.
    "gaps": {
        "horizontal": {
            "none": "my-0",
            "xs": "my-(--bz-gap-1)",
            "sm": "my-(--bz-gap-2)",
            "md": "my-(--bz-gap-4)",
            "lg": "my-(--bz-gap-6)",
            "xl": "my-(--bz-gap-8)",
        },
        "vertical": {
            "none": "mx-0",
            "xs": "mx-(--bz-gap-1)",
            "sm": "mx-(--bz-gap-2)",
            "md": "mx-(--bz-gap-4)",
            "lg": "mx-(--bz-gap-6)",
            "xl": "mx-(--bz-gap-8)",
        },
    },
    # Per-orientation overlays applied on top of the root + line slots.
    "orientations": {
        "horizontal": {
            "root": "flex-row w-full",
            "line": "h-0 w-full border-t-(length:--bz-stroke)",
        },
        "vertical": {
            "root": "flex-col h-full min-h-[1rem]",
            "line": "w-0 h-full border-l-(length:--bz-stroke)",
        },
    },
}
