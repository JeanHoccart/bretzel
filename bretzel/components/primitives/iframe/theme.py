"""Default :class:`Iframe` theme.

Same stance as ``image`` and ``video``: the root IS the ``<iframe>``,
with no wrapper. It carries ``aspect-ratio`` and a background itself, so
the waiting box is its own background.

The ratio counts more here than anywhere else. An embed is **the leading
cause of page jump**: the remote document takes hundreds of milliseconds
to answer, and with no reserved height everything that follows shifts
when it arrives. An ``<iframe>`` with no dimensions in fact falls back on
a 300×150 inherited from 1996, which nobody wants.

``bg-muted/30`` — the same as the image's, and not the video's black: an
embedded document is page content, not a medium graded against black. A
discreet border sets it apart from the page, because a third-party
document blending into yours is as misleading as it is illegible.

A **closed** and **copied** ratio table (the class strings stay per
component), classes written out in full — an f-string
``aspect-[{w}/{h}]`` would be invisible to the production Tailwind
compiler.
"""

from __future__ import annotations

from typing import Any

IFRAME_THEME: dict[str, Any] = {
    "slots": {
        # ``block``: an iframe is ``inline`` by default, which sticks
        # the baseline's space under its belly.
        "root": (
            "block max-w-full bg-muted/30 "
            "border-(length:--bz-stroke) border-text/10 rounded-box"
        ),
    },
    "ratios": {
        "square": "aspect-square w-full",
        "video": "aspect-video w-full",
        "portrait": "aspect-[3/4] w-full",
        "wide": "aspect-[21/9] w-full",
    },
}
