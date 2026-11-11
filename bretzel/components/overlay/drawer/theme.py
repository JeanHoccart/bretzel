"""Default :class:`Drawer` theme.

Side-anchored panel : full-height (or full-width for top/bottom)
slides in from one edge. Same surface identity as Dialog (``surface``
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
        # CSS-only enter on ``data-open`` (set by the runtime; element
        # stays mounted; a closed drawer is inert). The transition lives
        # on the OPEN state: it slides in, and closes at once (the why:
        # ``overlay/dialog/theme.py``).
        "backdrop": (
            "fixed inset-0 z-40 bg-black/50 backdrop-blur-sm "
            "data-[open=true]:transition-[opacity,visibility] data-[open=true]:duration-200 "
            "data-[open=false]:opacity-0 data-[open=false]:invisible "
            "data-[open=false]:pointer-events-none"
        ),
        # ``items-stretch`` so the panel can stretch on the cross axis
        # (full height on left/right, full width on top/bottom).
        "container": (
            "fixed inset-0 z-50 flex pointer-events-none "
            "data-[open=true]:transition-[visibility] data-[open=true]:duration-200 data-[open=false]:invisible"
        ),
        # Common panel surface — sides add the per-edge border + the
        # closed-state translate (``data-[open=false]:…``, applied in
        # render). ``translate`` is the v4 individual property (NOT
        # transform), same gotcha as the sidebar mobile slide.
        #
        # ``max-w-full max-h-full`` is the CONTAINMENT cap : whatever
        # ``widths`` asks for, the panel never leaves the viewport. It
        # clamps against the ``fixed inset-0`` container — i.e. the
        # viewport — and covers the two ways it would otherwise break :
        #   - HEIGHT (the loud one). ``lg``/``xl`` top/bottom drawers are
        #     384/512px tall and would run off a 375px-tall phone in
        #     landscape. Height is the cross axis here, so flex-shrink
        #     does not apply. A ``bottom`` one would put its header — and
        #     its close button — ABOVE the top edge : unclosable.
        #   - WIDTH (the quiet one). Left/right panels look safe because
        #     flex-shrink pulls ``w-96`` down to the viewport… until the
        #     content has a min-content width of its own. One unbreakable
        #     token (UUID, URL, path) and the panel snaps back to 384px
        #     on a 375px screen — silently, since a ``fixed`` subtree
        #     grows no document scrollbar to signal it.
        # Two classes, both load-bearing, and NOTHING else is needed
        # (``tests/probes/probe_mobile_overflow.py``).
        # ``min-w-0``/``min-h-0`` would be
        # redundant : ``body``'s ``overflow-y-auto`` already makes this a
        # scroll container, which drops the flexbox ``min-*: auto`` floor
        # and clips the overflowing token. Dialog does not have the bug
        # because it DERIVES its width from the container (``w-full
        # max-w-*``) instead of declaring a hard one.
        # ``bg-surface``, not ``bg-interface``: a panel that HOLDS fields
        # must not wear the fields' own fill — inside a dialog (and so a drawer) at
        # ``interface`` the inputs would vanish into it.
        # Three levels: ``background`` the page, ``surface`` a panel,
        # ``interface`` a control.
        "panel": (
            "pointer-events-auto bg-surface text-text "
            "border-text/10 shadow-xl flex flex-col "
            "max-w-full max-h-full "
            "data-[open=true]:transition-[translate,visibility] data-[open=true]:duration-200 data-[open=true]:ease-out "
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
    # scans the SOURCE files: it only knows literal strings. If this
    # table carried only ``translate-x-full`` and the component
    # wrote ``f"data-[open=false]:{closed}"``, the complete class would
    # exist **in no file** — so not in ``style.css`` either.
    #
    # In dev, ``@tailwindcss/browser`` scans the live DOM and generates
    # it: the drawer would slide. In prod, no translate at all, so no
    # animation — the panel would appear all at once. The emitted HTML is
    # identical on both sides, only the compiled sheet differs. Gated by
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
    # In ``rem``, like ``lg`` and ``xl``: a spacing step follows the
    # density, and would render ``sm``/``md`` narrower than their names.
    "widths": {
        "horizontal": {  # left / right
            "sm":   "w-[18rem]",
            "md":   "w-[24rem]",
            "lg":   "w-[28rem]",
            "xl":   "w-[36rem]",
            "full": "w-screen",
        },
        "vertical": {    # top / bottom
            "sm":   "h-[12rem]",
            "md":   "h-[18rem]",
            "lg":   "h-[24rem]",
            "xl":   "h-[32rem]",
            "full": "h-screen",
        },
    },
}
