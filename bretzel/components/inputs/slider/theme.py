"""Default :class:`Slider` theme.

Horizontal slider with a track, an active-fill segment, one or two
handles, and a hover/drag tooltip showing the live value. Mirrors
the visual identity of Input / Select : same border colour family,
same focus ring recipe, same 5-palier size scale.

Slots :
- ``root``    : outer wrapper that hosts the ``bz-data`` scope + hidden input
- ``track``   : the horizontal line the handle slides along
- ``fill``    : the coloured active portion of the track
- ``handle``  : the circular grip the user drags
- ``tooltip`` : the floating bubble above the handle that shows the
                live value during hover / focus / drag
"""

from __future__ import annotations

from typing import Any

SLIDER_THEME: dict[str, Any] = {
    "slots": {
        # The outer wrapper. ``select-none`` so the user can drag
        # the handle without browser text-selection getting in the
        # way (V1 idiom, ported). ``touch-none`` blocks the browser
        # from interpreting touch drags as scroll on mobile —
        # otherwise the slider fights with vertical scroll.
        "root": (
            "bz-slider "
            "relative w-full select-none touch-none "
            "py-2"
        ),
        # The track is the visual line. ``cursor-pointer`` so the
        # user knows they can click anywhere on it to jump the
        # closest handle there. ``rounded-full`` for the standard
        # capsule look.
        "track": (
            "relative w-full rounded-full bg-text/10 "
            "cursor-pointer"
        ),
        # The fill : a coloured slice of the track between min and
        # the current value (single) or between start and end
        # (range). Positioned absolute, width/left driven by
        # ``bz-attr:style``. ``transition-[width,left]`` makes keyboard
        # nudges glide smoothly ; drag updates skip the transition
        # via a ``data-dragging`` toggle.
        "fill": (
            "absolute top-0 left-0 h-full rounded-full "
            "bg-(--bz-solid) "
            # Decorative only : a click on the coloured slice must fall
            # THROUGH to the track (whose pointerdown jumps the nearest
            # handle). Without this the whole filled half of the slider
            # is dead to clicks — the track guards on
            # ``$event.target === $el`` and the fill would be the target.
            "pointer-events-none "
            "transition-[width,left] duration-100 ease-out "
            "data-[dragging=true]:transition-none"
        ),
        # The handle : the circular grip the user drags. Positioned
        # absolute via ``:style`` (left:N% + translateX(-50%) so the
        # handle's centre lands on the value's pixel exactly). The
        # focus ring is the same recipe as Input / Select for
        # consistency.
        "handle": (
            "absolute top-1/2 -translate-y-1/2 -translate-x-1/2 "
            "rounded-full bg-(--bz-solid) shadow-md "
            "border-(length:--bz-stroke-strong) border-background "
            "cursor-grab active:cursor-grabbing "
            "outline-none "
            "transition-[left,top] duration-100 ease-out "
            "data-[dragging=true]:transition-none "
            "focus-visible:ring-4 focus-visible:ring-(--bz-focus-soft) "
            "hover:scale-110 active:scale-110 "
            "disabled:opacity-50 disabled:cursor-not-allowed "
            "disabled:hover:scale-100"
        ),
        # The tooltip bubble above the handle. Hidden by default ;
        # ``bz-show`` flips on when the handle is hovered, focused,
        # or being dragged. Positioned absolute relative to the
        # handle (the handle is the offset parent).
        "tooltip": (
            "absolute bottom-full left-1/2 -translate-x-1/2 mb-2 "
            "px-2 py-0.5 rounded-selector "
            "bg-text text-background "
            "text-xs font-medium "
            "whitespace-nowrap pointer-events-none "
            "before:content-[''] before:absolute before:top-full "
            "before:left-1/2 before:-translate-x-1/2 "
            "before:border-(length:--bz-stroke-accent) before:border-transparent "
            "before:border-t-text"
        ),
    },
    # Sizes scale the track thickness + handle diameter. Vertical
    # padding on the root absorbs the handle's overshoot so the
    # slider's box doesn't squeeze adjacent form fields.
    "sizes": {
        "xs": {
            "track": "h-1",
            "handle": "h-3 w-3",
        },
        "sm": {
            "track": "h-1.5",
            "handle": "h-4 w-4",
        },
        "md": {
            "track": "h-2",
            "handle": "h-5 w-5",
        },
        "lg": {
            "track": "h-2.5",
            "handle": "h-6 w-6",
        },
        "xl": {
            "track": "h-3",
            "handle": "h-7 w-7",
        },
    },
}
