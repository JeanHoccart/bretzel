"""Default :class:`Dialog` theme.

Centered modal : translucent backdrop + card panel. Same identity
as Card — rounded-box + shadow + subtle border. Sizes scale max-width
in the reasonable web range (sm 24rem … xl 36rem (``max-w-xl``), ``2xl``
64rem for a settings-sized window, ``full`` fills the viewport with margin).

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
        # Enter is CSS-only, driven by ``data-open`` (set by the runtime).
        # The element stays mounted; closed = inert (invisible + no
        # pointer events, so a closed dialog can't be tabbed into).
        #
        # THE TRANSITION LIVES ON THE OPEN STATE (``data-[open=true]:``):
        # CSS takes the transition of the state it ARRIVES in, so opening
        # fades and closing drops at once — what disappears does not
        # linger, one chains on. Same rule for every overlay, chevron
        # and disclosure; ``duration`` is prefixed too, or the initial
        # ``transition-property: all`` would animate the close anyway.
        "backdrop": (
            "fixed inset-0 z-40 bg-black/50 backdrop-blur-sm "
            "data-[open=true]:transition-[opacity,visibility] data-[open=true]:duration-200 "
            "data-[open=false]:opacity-0 data-[open=false]:invisible "
            "data-[open=false]:pointer-events-none "
            # A dialog that ARRIVES open (rendered by a zone, ``open=True``)
            # has no closed state to leave: without ``@starting-style``
            # it would appear in one frame, unanimated.
            "starting:opacity-0"
        ),
        "container": (
            "fixed inset-0 z-50 flex items-center justify-center p-4 "
            "pointer-events-none data-[open=true]:transition-[visibility] data-[open=true]:duration-200 "
            "data-[open=false]:invisible"
        ),
        # ``scale`` (v4 individual prop, NOT transform) for the pop ;
        # ``data-[open=false]`` is the closed state, the base is open.
        # ``bg-surface``, not ``bg-interface``: a panel that HOLDS fields
        # must not wear the fields' own fill — inside a dialog at
        # ``interface`` the inputs would vanish into it.
        # Three levels: ``background`` the page, ``surface`` a panel,
        # ``interface`` a control.
        "panel": (
            "pointer-events-auto w-full bg-surface text-text "
            "rounded-box border-(length:--bz-stroke) border-text/10 shadow-xl "
            "flex flex-col max-h-[calc(100vh-2rem)] overflow-hidden "
            "data-[open=true]:transition-[opacity,scale,visibility] data-[open=true]:duration-200 data-[open=true]:ease-out "
            "data-[open=false]:opacity-0 data-[open=false]:scale-95 "
            "data-[open=false]:invisible data-[open=false]:pointer-events-none "
            "starting:opacity-0 starting:scale-95"
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
        # A window of settings, a two-column form: the step between a
        # form (``xl``) and the whole screen. Named like the container's
        # widest step.
        "2xl":  "max-w-5xl",  # 64rem
        "full": "max-w-none",
    },
}
