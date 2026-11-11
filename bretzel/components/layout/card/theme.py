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

``rounded-box`` + ``shadow-sm`` baseline + ``border-text/10`` hairline
border + ``bg-surface`` (white by default) — the standard look.

``overflow-hidden`` clips children that overflow the radius, but
careful : it ALSO clips popovers / dropdowns that escape the card.
"""

from __future__ import annotations

from typing import Any

CARD_THEME: dict[str, Any] = {
    "slots": {
        # ``text-(--bz-on-solid)`` is not decorative: without it,
        # ``color=`` would paint a BACKGROUND with no foreground, and the
        # text would keep the colour inherited from the page, illegible.
        # It is the ``<colour>-foreground`` convention of Badge / Button /
        # IconButton.
        # ⚠️ **No shadow AT REST.** A card placed in
        # the flow is not a floating layer: it is bounded by its hairline.
        # The shadow stays the vocabulary of real layers — dialog,
        # popover, dropdown — and of HOVER, where it says "this is
        # clickable". A shadow everywhere distinguishes nothing any
        # more.
        "root": (
            "block w-full rounded-box overflow-hidden "
            "bg-(--bz-solid) text-(--bz-on-solid) border-(length:--bz-stroke) border-text/10"
        ),
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
    # When ``hoverable=True`` (or ``href=`` is set, which auto-enables
    # hoverable), the lift effect kicks in. NOTE : do NOT gate on
    # ``aria-enabled:`` — it is NOT a Tailwind variant (only
    # aria-checked/disabled/expanded/… are built in) AND the Card never
    # emits that attribute, so the whole lift silently never compiled.
    # Plain ``hover:`` lifts ; a "locked surface" (app sets
    # ``aria-disabled="true"`` via attrs=) NEUTRALISES the lift by
    # specificity — ``aria-disabled:hover:*`` (0,3,0) beats ``hover:*``
    # (0,2,0). aria-disabled IS a built-in variant. Cf. the Link
    # disabled fix.
    "hoverable": (
        "transition duration-150 ease-out cursor-pointer "
        "relative top-0 "
        "hover:shadow-sm "
        "hover:border-text/20 "
        "hover:-top-px "
        "aria-disabled:cursor-default "
        "aria-disabled:hover:top-0 "
        "aria-disabled:hover:shadow-none "
        "aria-disabled:hover:border-text/10"
    ),
    # A card one acts on (``on_click=`` or ``href=``) is reached with Tab:
    # it shows it, like a button does. Cf. ``card.py``.
    "focusable": (
        "focus-visible:outline-none focus-visible:ring-2 "
        "focus-visible:ring-(--bz-focus) focus-visible:ring-offset-2 "
        "focus-visible:ring-offset-background"
    ),
}
