"""Default :class:`IconButton` theme.

Square sibling of Button : same variants + focus/active feedback, but the
size axis controls ``h × w`` together (no label to centre against).
``rounded-field`` matches Button's radius so the two sit side by side.
"""

from __future__ import annotations

from typing import Any

ICON_BUTTON_THEME: dict[str, Any] = {
    "slots": {
        "root": (
            "inline-flex items-center justify-center "
            "rounded-field font-medium "
            "transition-all duration-200 ease-out "
            "not-disabled:active:scale-[0.95] "
            "focus-visible:outline-none focus-visible:ring-2 "
            "focus-visible:ring-offset-2 focus-visible:ring-offset-background "
            "focus-visible:ring-(--bz-focus) "
            "disabled:opacity-50 disabled:cursor-not-allowed"
        ),
    },
    "variants": {
        "solid": (
            "bg-(--bz-solid) text-(--bz-on-solid) shadow-sm "
            "not-disabled:hover:brightness-110 not-disabled:hover:shadow-md"
        ),
        "outline": (
            "border-(length:--bz-stroke-strong) border-(--bz-solid) text-(--bz-text) "
            "not-disabled:hover:bg-(--bz-bg)"
        ),
        "ghost": (
            "text-(--bz-text) "
            "not-disabled:hover:bg-(--bz-bg)"
        ),
        # Surface: the control reads as a FIELD — the same bordered box
        # as ``ui.input``. It is what was missing for a toolbar mixing a
        # search and buttons to read as ONE family: `soft` gives a wash
        # with no border, `outline` an accented 2 px border, and neither
        # of the two resembles the neighbouring field (`bg-interface` +
        # `border-text/10`).
        #
        # The colour stays a hook (`text-(--bz-text)`) so the "the accent
        # marks the ACTIVE peer" rule goes on applying without changing
        # the box: at rest `current`, active the accent — the geometry
        # does not move.
        "surface": (
            "bg-interface border-(length:--bz-stroke) border-text/10 text-(--bz-text) "
            "not-disabled:hover:bg-text/5"
        ),
        "soft": (
            "bg-(--bz-bg) text-(--bz-text) "
            "not-disabled:hover:bg-(--bz-bg-hover)"
        ),
    },
    # Square sizing : ``h-N w-N`` for a balanced click target. ``text-N``
    # controls the inner icon size via ``font-size`` (Iconify sizes in ``1em``).
    "sizes": {
        "xs": "h-7 w-7 text-xs",
        "sm": "h-8 w-8 text-sm",
        "md": "h-10 w-10 text-base",
        "lg": "h-12 w-12 text-lg",
        "xl": "h-14 w-14 text-xl",
    },
}
