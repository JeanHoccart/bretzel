"""Default :class:`Card` theme.

Signature lift effect : the card pops 1px on hover with a deeper
shadow + a coloured border tint. Subtle, but it's what makes a
clickable card feel like a click target.

⚠️ The lift is ``relative top-0 hover:-top-0.5`` — a POSITION offset,
deliberately NOT ``hover:-translate-y-0.5``. A
``translate``/``transform`` makes the card a CONTAINING BLOCK for
``position:fixed`` descendants : any anchored overlay (Select panel,
Tooltip…) opened while the pointer is on the card — i.e. always, the
click IS a hover — paints double-offset (~card.top too low) and gets
clippable by the card's ``overflow-hidden``. A ``top`` offset animates
identically and creates no containing block. Cf. traps.md § « Un overlay
hérite des contraintes de ses ancêtres ».

``rounded-box`` + ``border-text/10`` hairline border + ``bg-surface``
(white by default) — the ``solid`` look. ``ghost`` drops the box: a row
of a list.

``overflow-hidden`` clips children that overflow the radius, but
careful : it ALSO clips popovers / dropdowns that escape the card.
"""

from __future__ import annotations

from typing import Any

CARD_THEME: dict[str, Any] = {
    "slots": {
        # ⚠️ **No shadow AT REST.** A card placed in
        # the flow is not a floating layer: it is bounded by its hairline.
        # The shadow stays the vocabulary of real layers — dialog,
        # popover, dropdown — and of HOVER, where it says "this is
        # clickable". A shadow everywhere distinguishes nothing any
        # more.
        "root": "block w-full rounded-box overflow-hidden",
    },
    # ``solid``: the bordered surface. ``ghost``: no background, border or
    # shadow — a row of a list, whose column already draws the frame; a
    # list and framed cards coexist in one screen (a mail list beside the
    # open mail), which is what earns it a variant (R2).
    #
    # A row is a dict, like a field's ``ghost``: ``root`` is the resting
    # look, ``hoverable`` what a card that acts shows under the pointer,
    # ``focusable`` its keyboard ring (``on_click=`` or ``href=``). The
    # render composes each one by name (``compose_class``).
    "variants": {
        "solid": {
            # ``text-(--bz-on-solid)`` is not decorative: without it,
            # ``color=`` would paint a BACKGROUND with no foreground, and
            # the text would keep the colour inherited from the page,
            # illegible. It is the ``<colour>-foreground`` convention of
            # Badge / Button / IconButton.
            "root": (
                "bg-(--bz-solid) text-(--bz-on-solid) "
                "border-(length:--bz-stroke) border-line"
            ),
            # The lift. NOTE : do NOT gate on ``aria-enabled:`` — it is NOT
            # a Tailwind variant (only aria-checked/disabled/expanded/…
            # are built in) AND the Card never emits that attribute, so the
            # whole lift silently never compiled. Plain ``hover:`` lifts ;
            # a "locked surface" (app sets ``aria-disabled="true"`` via
            # attrs=) NEUTRALISES the lift by specificity —
            # ``aria-disabled:hover:*`` (0,3,0) beats ``hover:*`` (0,2,0).
            "hoverable": (
                "transition duration-150 ease-out cursor-pointer "
                "relative top-0 "
                "hover:shadow-sm "
                "hover:border-line-strong "
                "hover:-top-px "
                "aria-disabled:cursor-default "
                "aria-disabled:hover:top-0 "
                "aria-disabled:hover:shadow-none "
                "aria-disabled:hover:border-line"
            ),
            "focusable": (
                "focus-visible:outline-none focus-visible:ring-2 "
                "focus-visible:ring-(--bz-focus) focus-visible:ring-offset-2 "
                "focus-visible:ring-offset-background"
            ),
        },
        "ghost": {
            "root": "bg-transparent",
            # It says it acts by its BACKGROUND, not by a lift: a row that
            # rises makes the whole list jump. The row lights at once, with
            # no fade (the sidebar's rows do the same).
            "hoverable": (
                "cursor-pointer hover:bg-hover "
                "aria-disabled:cursor-default aria-disabled:hover:bg-transparent"
            ),
            # The ring is drawn INSIDE: a list lives in a column that
            # scrolls, and an outer ring would be cut by it (traps.md, the
            # ring clipped by a scrolling column). Its colour is the
            # accent's, as the active row's: the card's own colour
            # (``surface`` by default) would draw a white ring on a white
            # page.
            "focusable": (
                "focus-visible:outline-none focus-visible:ring-2 "
                "focus-visible:ring-inset focus-visible:ring-primary-ring"
            ),
        },
    },
    # Padding scale, responsive (smaller on mobile).
    "paddings": {
        "none": "",
        "xs": "p-(--bz-pad-2) sm:p-(--bz-pad-3)",
        "sm": "p-(--bz-pad-3) sm:p-(--bz-pad-4)",
        "md": "p-(--bz-pad-4) sm:p-(--bz-pad-6)",  # default
        "lg": "p-(--bz-pad-6) sm:p-(--bz-pad-8)",
        "xl": "p-(--bz-pad-8) sm:p-(--bz-pad-10)",
    },
    # ``active=True``: the chosen element of a list (R1's word: the
    # sidebar's, the navbar's) — the accent's background. Written under
    # ``data-[active=true]:`` so it outranks the variant's background and
    # the hover's (0,2,0 and 0,3,0 against 0,1,0 and 0,2,0), whatever the
    # order of the compiled sheet. The text goes back to the page's, for a
    # coloured ``solid`` card whose light text would not read on the tint.
    "active": (
        "data-[active=true]:bg-primary-wash data-[active=true]:hover:bg-primary-wash-hover "
        "data-[active=true]:text-text"
    ),
}
