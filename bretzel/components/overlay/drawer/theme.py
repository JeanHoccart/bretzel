"""Default :class:`Drawer` theme.

Side-anchored panel : full-height (or full-width for top/bottom)
slides in from one edge. Same surface identity as Dialog (interface
bg + soft border) so they sit in the same visual family ; only the
positioning + transition differ.

Slots :
- ``backdrop``   : full-screen dim layer
- ``container``  : ``fixed inset-0`` flex wrapper that anchors the
                   panel to its side
- ``panel``      : the sliding card itself
- ``header``     : top row (title + close)
- ``title``      : heading text
- ``close``      : the X button on the right
- ``body``       : main content area
"""

from __future__ import annotations

from typing import Any

DRAWER_THEME: dict[str, Any] = {
    "slots": {
        # CSS-only enter/leave on ``data-open`` (set by the runtime ;
        # element stays mounted). ``visibility`` rides the transition so
        # it holds ``visible`` through the slide-out then flips ``hidden``
        # (a closed drawer is inert : invisible + no pointer events).
        "backdrop": (
            "fixed inset-0 z-40 bg-black/50 backdrop-blur-sm "
            "transition-[opacity,visibility] duration-200 "
            "data-[open=false]:opacity-0 data-[open=false]:invisible "
            "data-[open=false]:pointer-events-none"
        ),
        # ``items-stretch`` so the panel can stretch on the cross axis
        # (full height on left/right, full width on top/bottom).
        "container": (
            "fixed inset-0 z-50 flex pointer-events-none "
            "transition-[visibility] duration-300 data-[open=false]:invisible"
        ),
        # Common panel surface — sides add the per-edge border + the
        # closed-state translate (``data-[open=false]:…``, applied in
        # render). ``translate`` is the v4 individual property (NOT
        # transform), same gotcha as the sidebar mobile slide.
        #
        # ``max-w-full max-h-full`` is the CONTAINMENT cap : whatever
        # ``widths`` asks for, the panel never leaves the viewport. It
        # clamps against the ``fixed inset-0`` container — i.e. the
        # viewport — and covers the two ways this used to break :
        #   - HEIGHT (the loud one). ``lg``/``xl`` top/bottom drawers are
        #     384/512px tall and simply ran off a 375px-tall phone in
        #     landscape. Height is the cross axis here, so flex-shrink
        #     never applied. A ``bottom`` one put its header — and its
        #     close button — 137px ABOVE the top edge : unclosable.
        #   - WIDTH (the quiet one). Left/right panels look safe because
        #     flex-shrink pulls ``w-96`` down to the viewport… until the
        #     content has a min-content width of its own. One unbreakable
        #     token (UUID, URL, path) and the panel snapped back to 384px
        #     on a 375px screen — silently, since a ``fixed`` subtree
        #     grows no document scrollbar to signal it.
        # Two classes, both load-bearing, and NOTHING else is needed —
        # verified by mutation (``tests/probes/probe_mobile_overflow.py``,
        # 10 failures with them off). ``min-w-0``/``min-h-0`` would be
        # redundant : ``body``'s ``overflow-y-auto`` already makes this a
        # scroll container, which drops the flexbox ``min-*: auto`` floor
        # and clips the overflowing token. Dialog never had the bug at all
        # because it DERIVES its width from the container (``w-full
        # max-w-*``) instead of declaring a hard one.
        "panel": (
            "pointer-events-auto bg-interface text-text "
            "border-text/10 shadow-xl flex flex-col "
            "max-w-full max-h-full "
            "transition-[translate,visibility] duration-300 ease-out "
            "data-[open=false]:invisible data-[open=false]:pointer-events-none"
        ),
        "header": (
            "flex items-start gap-3 px-5 py-4 border-b-(length:--bz-stroke) border-text/5"
        ),
        "title": "flex-1 text-lg font-semibold leading-snug",
        "close": "shrink-0 -mr-1 -mt-1",
        "body": "flex-1 overflow-y-auto px-5 py-4",
    },
    # Per-side container alignment + panel border + CLOSED translate.
    # ``border-l`` / ``border-r`` etc. picks up the panel's
    # ``border-text/10`` so the edge against the page is hairlined.
    # ``closed`` is the off-screen translate, applied to the closed
    # state; open = no translate (the panel slid into place).
    #
    # ⚠️ It carries the WHOLE variant, ``data-[open=false]:`` included,
    # and that is not a redundancy. The production Tailwind compiler
    # scans the SOURCE files: it only knows literal strings. As long as
    # this table carried only ``translate-x-full`` and the component
    # wrote ``f"data-[open=false]:{closed}"``, the complete class existed
    # **in no file** — so not in ``style.css`` either.
    #
    # In dev, ``@tailwindcss/browser`` scans the live DOM and generates
    # it: the drawer slid. In prod, no translate at all, so no animation
    # — the panel appeared all at once. Reported on 2026-08-07, invisible
    # to every suite: the emitted HTML is identical on both sides, only
    # the compiled sheet differs. Gated by
    # ``tests/consistency/test_emitted_classes_exist_in_source.py``.
    "sides": {
        "left":   {"container": "justify-start", "panel": "h-full border-r-(length:--bz-stroke)", "closed": "data-[open=false]:-translate-x-full"},
        "right":  {"container": "justify-end",   "panel": "h-full border-l-(length:--bz-stroke)", "closed": "data-[open=false]:translate-x-full"},
        "top":    {"container": "items-start",   "panel": "w-full border-b-(length:--bz-stroke)", "closed": "data-[open=false]:-translate-y-full"},
        "bottom": {"container": "items-end",     "panel": "w-full border-t-(length:--bz-stroke)", "closed": "data-[open=false]:translate-y-full"},
    },
    # ``widths`` clamp the dimension perpendicular to the anchor edge.
    # Left/right sides clamp the actual width ; top/bottom sides clamp
    # the height. The component picks the right axis from ``side`` at
    # render time.
    "widths": {
        "horizontal": {  # left / right
            "sm":   "w-72",
            "md":   "w-96",
            "lg":   "w-[28rem]",
            "xl":   "w-[36rem]",
            "full": "w-screen",
        },
        "vertical": {    # top / bottom
            "sm":   "h-48",
            "md":   "h-72",
            "lg":   "h-96",
            "xl":   "h-[32rem]",
            "full": "h-screen",
        },
    },
}
