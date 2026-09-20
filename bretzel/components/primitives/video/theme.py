"""Default :class:`Video` theme.

Same stance as :mod:`bretzel.components.primitives.image.theme`: the
root **is** the media element, with no wrapper. A ``<video>`` carries
``aspect-ratio``, ``object-fit`` and a background itself, so the waiting
box is its own background.

What that gives with no line of JS:

- **before the metadata arrive**, the box at the declared ratio already
  takes its place. A video is the worst case of page jump: the browser
  only knows its dimensions after a network round trip, so without
  ``ratio`` everything that follows shifts a second later;
- **if the source breaks**, the same box stays.

The background is ``bg-black`` and not the image's ``bg-muted/30`` — a
FIXED palette colour, so an exception to the semantic-token rule,
declared in ``test_themes_use_semantic_colours``.

The reason: that black is not a surface of the page, it is a **medium's
surface**. Letterboxing bars are black in every player, in both modes,
because video is graded against black. A ``bg-muted/30`` would give
light grey bars around a dark image in light mode, which is the wrong
render — not the "theme-aware" one.


⚠️ **The ratio table is COPIED from the image's theme, on purpose.**
Visual class strings stay per component in this repository — a shared
style token would couple two themes that must be able to diverge (the
day a video wants a cinema ratio the image does not have). The
convention is harmonised, not factored out.

And as at the image: a **closed** table, classes written out in full. An
f-string ``aspect-[{w}/{h}]`` would be invisible to the production
Tailwind compiler — it would work in dev and disappear at deployment.
"""

from __future__ import annotations

from typing import Any

VIDEO_THEME: dict[str, Any] = {
    "slots": {
        # ``block``: a media element is ``inline`` by default, which
        # sticks the baseline's space under its belly.
        # ``bg-black``: THE background that serves as the waiting box
        # (cf. the docstring).
        "root": "block max-w-full bg-black",
    },
    "ratios": {
        "square": "aspect-square w-full",
        "video": "aspect-video w-full",
        "portrait": "aspect-[3/4] w-full",
        "wide": "aspect-[21/9] w-full",
    },
    # How the medium's picture fills the declared ratio. ``contain`` is
    # the default here, the OPPOSITE of ``ui.image``: cropping a photo is
    # harmless, cropping a video cuts the action — letterboxing is the
    # behaviour expected of any player.
    "fits": {
        "contain": "object-contain",
        "cover": "object-cover",
    },
}
