"""Default :class:`Switch` theme.

Same invisible ``peer`` input idiom as the checkbox, but the visual is a rail
(``track``) with a sliding pill (``thumb``).
The slide is animated via ``transition-transform`` on the thumb's
``translate-x-N`` triggered by ``peer-checked``.

Slots :
- ``root``     : ``<label>`` clickable wrapper
- ``container``: relative wrapper aligning track + thumb
- ``input``    : visually-hidden real ``<input>`` (``peer``)
- ``track``    : the rail ; fills with ``--bz-solid`` on check
- ``thumb``    : the white pill that slides
- ``label``    : text next to the rail
"""

from __future__ import annotations

from typing import Any

SWITCH_THEME: dict[str, Any] = {
    "slots": {
        "root": (
            "bz-switch "
            "inline-flex items-center align-middle gap-3 group select-none cursor-pointer "
            # Disabled visual — fully CSS-reactive via the hidden peer
            # ``<input disabled>`` descendant. Same shape as Checkbox /
            # Radio so the family stays uniform.
            "has-[:disabled]:opacity-50 "
            "has-[:disabled]:cursor-not-allowed"
        ),
        "container": "relative inline-flex items-center shrink-0",
        "input": "peer absolute inset-0 m-0 opacity-0 z-10 cursor-pointer disabled:cursor-not-allowed",
        "track": (
            "block rounded-full border-(length:--bz-stroke) border-text/10 bg-interface "
            "transition duration-200 ease-out "
            "peer-checked:bg-(--bz-solid) peer-checked:border-(--bz-solid) "
            "peer-focus-visible:ring-2 peer-focus-visible:ring-(--bz-focus) "
            "peer-focus-visible:ring-offset-2 "
            "peer-focus-visible:ring-offset-background"
        ),
        # The thumb is ``absolute`` and the track is ``block`` (out of the
        # thumb's flow), so without an explicit ``top`` the thumb falls to
        # the bottom of the rail. ``transition-transform`` so the slide
        # is the only animated property — colour swaps stay in their lane.
        # Inset by HALF A STEP, not by a pixel literal. Every size is a
        # track one step taller than its thumb and ``thumb + travel + 1``
        # steps wide, so half a step on each side centres the thumb at
        # any density; a pixel literal is half a step at one density only.
        # ``test_the_switch_thumb_is_centred_by_construction`` holds it.
        # Vertically, centred on the CONTAINER (``top-1/2
        # -translate-y-1/2``), where the track is centred too: beside a
        # label the container is at least one line high (``min-h-[1lh]``),
        # taller than an ``xs`` rail, and ``top-0.5`` would sit the thumb
        # low.
        "thumb": (
            "absolute start-0.5 top-1/2 -translate-y-1/2 inline-block rounded-full "
            "bg-white shadow-sm "
            "transition-transform duration-200 ease-out"
        ),
        "label": (
            "font-medium text-text transition duration-200 "
            "group-has-[input:not(:disabled)]:group-hover:opacity-70"
        ),
    },
    # Per-size dict : track dimensions, thumb dimensions, slide
    # distance (``peer-checked:translate-x-N``), label text size.
    "sizes": {
        "xs": {
            "track": "h-3 w-5",
            "thumb": "h-2 w-2 peer-checked:translate-x-2",
            "label": "text-xs",
        },
        "sm": {
            "track": "h-4 w-7",
            "thumb": "h-3 w-3 peer-checked:translate-x-3",
            "label": "text-xs",
        },
        "md": {
            "track": "h-5 w-9",
            "thumb": "h-4 w-4 peer-checked:translate-x-4",
            "label": "text-sm",
        },
        "lg": {
            "track": "h-6 w-11",
            "thumb": "h-5 w-5 peer-checked:translate-x-5",
            "label": "text-base",
        },
        "xl": {
            "track": "h-7 w-13",
            "thumb": "h-6 w-6 peer-checked:translate-x-6",
            "label": "text-lg",
        },
    },
}
