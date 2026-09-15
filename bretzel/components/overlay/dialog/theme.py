"""Default :class:`Dialog` theme.

Centered modal : translucent backdrop + card panel. Same identity
as Card — rounded-box + shadow + subtle border. Sizes scale max-width
in the reasonable web range (sm 24rem … xl 36rem (``max-w-xl``), ``full`` fills the
viewport with margin).

Slots :
- ``backdrop``   : full-screen dim layer behind the panel
- ``container``  : flex centering wrapper
- ``panel``      : the dialog card itself
- ``header``     : top row (title + close button)
- ``title``      : the heading text
- ``close``      : the X button on the right of the header
- ``body``       : main content area
"""

from __future__ import annotations

from typing import Any

DIALOG_THEME: dict[str, Any] = {
    "slots": {
        # Enter/leave is CSS-only, driven by ``data-open`` (set by the
        # runtime). The element stays mounted ; ``visibility`` is in the
        # transition so it holds ``visible`` through the fade-out then
        # flips ``hidden`` (closed = inert : invisible + no pointer events,
        # so a closed dialog can't be tabbed into).
        "backdrop": (
            "fixed inset-0 z-40 bg-black/50 backdrop-blur-sm "
            "transition-[opacity,visibility] duration-200 "
            "data-[open=false]:opacity-0 data-[open=false]:invisible "
            "data-[open=false]:pointer-events-none"
        ),
        "container": (
            "fixed inset-0 z-50 flex items-center justify-center p-4 "
            "pointer-events-none transition-[visibility] duration-200 "
            "data-[open=false]:invisible"
        ),
        # ``scale`` (v4 individual prop, NOT transform) for the pop ;
        # ``data-[open=false]`` is the closed state, the base is open.
        "panel": (
            "pointer-events-auto w-full bg-interface text-text "
            "rounded-box border-(length:--bz-stroke) border-text/10 shadow-xl "
            "flex flex-col max-h-[calc(100vh-2rem)] overflow-hidden "
            "transition-[opacity,scale,visibility] duration-200 ease-out "
            "data-[open=false]:opacity-0 data-[open=false]:scale-95 "
            "data-[open=false]:invisible data-[open=false]:pointer-events-none"
        ),
        "header": (
            "flex items-start gap-3 px-5 py-4 border-b-(length:--bz-stroke) border-text/5"
        ),
        "title": "flex-1 text-lg font-semibold leading-snug",
        "close": "shrink-0 -mr-1 -mt-1",
        "body": "flex-1 overflow-y-auto px-5 py-4",
    },
    # ``max-w`` per size. ``full`` keeps the 1rem margin from the
    # container's ``p-4`` so the card doesn't touch the viewport edges.
    "widths": {
        "sm":   "max-w-sm",   # 24rem
        "md":   "max-w-md",   # 28rem
        "lg":   "max-w-lg",   # 32rem
        "xl":   "max-w-xl",   # 36rem
        "full": "max-w-none",
    },
}
