"""Default :class:`Badge` theme.

Small inline label : softly-rounded background or solid fill,
sometimes carrying an inline icon, optionally dismissible via a
trailing ``×`` button (``dismissible=True`` or ``on_close``).

Slots :
- ``root``        : the pill itself
- ``label``       : the inline text (truncates on long labels)
- ``close``       : the ``×`` button (rendered as soon as
                    ``dismissible=True`` OR ``on_close`` is passed — not
                    only ``on_close``)

The sizing of the close button's icon is NOT a slot: it lives in
``sizes[size]["close_icon_size"]``.

Note : no ``icon`` slot — Badge's leading/trailing icons are pre-built
:class:`Icon` instances sized via the theme's ``sizes[size].icon_size``
(``Component.adopt_slot(icon_size=…)`` in ``badge.py``). Their own class handles styling.

Variants :
- ``soft``    : tinted bg + coloured text (default — subtle)
- ``solid``   : full bg + foreground text (stronger emphasis)
- ``outline`` : coloured border + text, transparent fill

Radius — ``rounded-selector`` (not a pill) so it reads as "label / chip"
and pairs with the form components, not as a "tracker / counter".
"""

from __future__ import annotations

from typing import Any

BADGE_THEME: dict[str, Any] = {
    "slots": {
        # ``max-w`` is what makes the label's ``truncate`` fire — a pill
        # with no width bound just grows to fit and the ellipsis never
        # triggers. Cf. the ``truncate ⇒ width-bound`` drift gate.
        # ``leading-normal`` (NOT ``leading-none``) : with ``line-height:1``
        # the ``truncate`` overflow:hidden clips descenders (y/g/p) ~2px ;
        # the fixed ``h-*`` + ``items-center`` make the roomier line-height
        # visually free.
        # ``w-fit`` : as a direct child of a flex parent (``ui.vstack`` /
        # ``ui.hstack``) the CSS spec blockifies ``inline-flex`` → ``flex``,
        # and the stack's default ``align-items: stretch`` then balloons the
        # pill to the full cross-axis width. ``width: fit-content`` pins it
        # back to its content regardless of container. Same class of bug —
        # and same fix — as the date_picker ``w-fit`` overflow.
        "root": (
            # ``min(16rem,100%)`` and not ``max-w-[16rem]`` alone: a
            # FIXED ceiling does not know its container, so it lets the
            # chip out of it, over the neighbour, as soon as the column is
            # narrower than it.
            #
            # ONE class, not two: ``max-w-full max-w-[16rem]`` both set
            # ``max-width`` and the winner depends on the SHEET's order,
            # not on the classes'.
            # ``tabular-nums``: a badge almost always carries a COUNTER,
            # and proportional digits do not have the same width — the
            # "1" is narrower than the "8". So the chip changes width at
            # every increment, and the line containing it jitters.
            "inline-flex w-fit items-center gap-1 max-w-[min(16rem,100%)] "
            "rounded-selector font-medium leading-normal tabular-nums "
            "whitespace-nowrap "
            "transition-colors duration-150"
        ),
        "label": "truncate",
        "close": (
            "shrink-0 inline-flex items-center justify-center "
            "rounded-selector cursor-pointer "
            "outline-none "
            "focus-visible:ring-2 focus-visible:ring-(--bz-focus) "
            "transition-colors duration-150"
        ),
    },
    # Multi-slot variants — each variant tweaks both the root AND
    # the close button so the × stays legible against its bg.
    "variants": {
        "soft": {
            "root": "bg-(--bz-bg) text-(--bz-text)",
            "close": (
                "text-(--bz-text-muted) hover:text-(--bz-text) "
                "hover:bg-(--bz-bg-hover)"
            ),
        },
        "solid": {
            "root": "bg-(--bz-solid) text-(--bz-on-solid)",
            "close": (
                "text-(--bz-on-solid) opacity-80 hover:opacity-100 "
                "hover:bg-black/10"
            ),
        },
        "outline": {
            # The border is the colour itself, as on a button's outline:
            # one colour for the frame and its label, the label being the
            # colour made readable — the colour itself wherever it reads
            # (``bridges.readable_step_pct``).
            "root": "border-(length:--bz-stroke-strong) border-(--bz-solid) text-(--bz-text)",
            "close": (
                "text-(--bz-text-muted) hover:text-(--bz-text) "
                "hover:bg-(--bz-bg)"
            ),
        },
    },
    "sizes": {
        "xs": {
            "root": "px-1.5 py-0 text-xs h-4",
            "close": "h-3 w-3",
            "icon_size": "xs",
            "close_icon_size": "xs",
        },
        "sm": {
            "root": "px-2 py-0.5 text-xs h-5",
            "close": "h-3.5 w-3.5",
            "icon_size": "xs",
            "close_icon_size": "xs",
        },
        "md": {
            "root": "px-2 py-0.5 text-sm h-6",
            "close": "h-4 w-4",
            "icon_size": "sm",
            "close_icon_size": "xs",
        },
        "lg": {
            "root": "px-2.5 py-1 text-sm h-7",
            "close": "h-5 w-5",
            "icon_size": "sm",
            "close_icon_size": "sm",
        },
        "xl": {
            "root": "px-3 py-1 text-base h-8",
            "close": "h-5 w-5",
            "icon_size": "md",
            "close_icon_size": "sm",
        },
    },
}
