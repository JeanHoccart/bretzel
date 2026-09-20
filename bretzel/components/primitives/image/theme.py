"""Default :class:`Image` theme.

A single slot, because the component is a single element: the root **is**
the ``<img>``. There is no wrapper, and that is the central design point
— an ``<img>`` carries ``aspect-ratio``, ``object-fit`` and a background
itself, so the loading "box" is its own background.

What that gives for free, with no line of JS:

- **before loading** — the box at the declared ratio already takes its
  place, in ``bg-muted/30``. It is the skeleton, and it is the same grey
  as ``ui.skeleton`` (the nearest semantic neighbour: both say "there
  will be something here");
- **if the URL breaks** — the same box stays. The browser puts its
  broken icon and the ``alt`` text over it, but the layout does not
  move.

That is why there is neither a ``skeleton`` prop nor a ``fallback``
prop: both states are the same object, and that object is the image's
background.

⚠️ **The ratios are a CLOSED table, written out in full.** An f-string
composing ``aspect-[{w}/{h}]`` would produce a class the Tailwind
compiler never sees — it would work in dev (browser compiler) and
disappear in prod, with identical HTML on both sides. A ratio outside
the table is asked for on the app side as ``classes="aspect-[5/2]"``,
where Tailwind scans it. Cf. the memory
``assembled_tailwind_class_dev_only``.
"""

from __future__ import annotations

from typing import Any

IMAGE_THEME: dict[str, Any] = {
    "slots": {
        # ``block``: an image is ``inline`` by default, which sticks the
        # baseline's space under its belly — a ghost sliver of a few
        # pixels in every card that surrounds it.
        # ``max-w-full``: never a horizontal overflow of the parent.
        # ``bg-muted/30``: THE background that serves as skeleton AND as
        # fallback.
        "root": "block max-w-full bg-muted/30",
    },
    # A closed table — cf. the docstring's warning.
    # ``w-full`` accompanies every ratio: ``aspect-ratio`` needs ONE
    # dimension to derive the other. With no ratio, the image keeps its
    # natural size and gets none of these classes.
    "ratios": {
        "square": "aspect-square w-full",
        "video": "aspect-video w-full",
        "portrait": "aspect-[3/4] w-full",
        "wide": "aspect-[21/9] w-full",
    },
    # How the image fills the ratio. With no ``object-*``, an image
    # whose natural ratio differs from the declared one is STRETCHED —
    # that is why ``fit`` has a default value rather than being
    # optional.
    "fits": {
        "cover": "object-cover",
        "contain": "object-contain",
    },
}
