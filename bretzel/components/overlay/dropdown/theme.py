"""Default :class:`Dropdown` + :class:`DropdownItem` theme.

Composition pattern : Dropdown wraps a Popover-style panel ; each
``DropdownItem`` is a button-row inside that panel. Same surface
identity as Popover (rounded card + border + shadow).

Slots — Dropdown :
- ``root``    : ``relative inline-flex`` wrapper holding trigger +
                panel (mirrors Popover's root)
- ``panel``   : floating card with item rows

Slots — DropdownItem :
- ``root``      : flex row, full width, hoverable
- ``icon_left`` : leading icon container
- ``label``     : item text, truncate
- ``icon_right``: trailing icon container
- ``shortcut``  : muted keyboard-shortcut hint at the right edge
"""

from __future__ import annotations

from typing import Any

DROPDOWN_THEME: dict[str, Any] = {
    "slots": {
        "root": "relative inline-flex w-fit h-fit",
        # ``min-w-[12rem]`` so the panel doesn't squish to its
        # narrowest item ; ``py-1`` spaces from the panel border so
        # hover backgrounds don't touch the rounded corners.
        "panel": (
            "absolute z-40 min-w-[12rem] py-1 "
            "rounded-box border-(length:--bz-stroke) border-text/10 bg-interface "
            "shadow-lg "
            # THE ENTER FADE OF AN ANCHORED PANEL — the family's
            # reference; the five other panels point here.
            #
            # ``display`` does not transition, and the runtime opens a
            # panel by writing ``style.display`` inline. A
            # ``transition-opacity`` alone therefore animated NOTHING:
            # seven carriers measured at constant opacity on 2026-09-04,
            # the class present from the start.
            #
            # The three go TOGETHER, and none serves alone:
            #   - ``display`` in the list of properties;
            #   - ``transition-discrete`` (``allow-discrete``), which
            #     holds ``display`` until the end of the fade;
            #   - ``starting:opacity-0``, the starting state — without it
            #     there is nothing to start from, the element is born
            #     at 1.
            #
            # AN INSTANT EXIT, and it is intended. ``@starting-style``
            # only gives the entry (measured: 9 frames at opacity 1 on
            # closing). A leaving fade would ask for the closed state in
            # CSS, so a mirrored ``data-open`` like ``dialog``'s — and a
            # menu that lingers reads as latency, not as care.
            #
            # Guarded by ``test_a_declared_transition_can_animate``.
            # Detail and measurements: traps.md § "a DECLARED transition".
            "transition-[opacity,display] transition-discrete duration-150 "
            "starting:opacity-0"
        ),
    },
}


DROPDOWN_ITEM_THEME: dict[str, Any] = {
    "slots": {
        # The hover / focus BG lives in ``colors`` (incl. the ``neutral``
        # default), NOT here — so a coloured row's tint wins cleanly with no
        # ``hover:bg-text`` vs ``hover:bg-error`` clash. Plain ``hover:`` (not
        # ``not-disabled:hover:``) so ``<a>`` link rows tint too (``:enabled`` /
        # ``:disabled`` don't exist on an ``<a>``).
        # Disabled : aria-only (MenuItem drops the native ``disabled`` attr
        # and strips the handlers, so the row is inert while the hit-test
        # stays live). NO ``pointer-events-none`` — it would suppress the
        # hover cursor. ``cursor-not-allowed`` then actually paints.
        "root": (
            "flex items-center gap-2 w-full text-start "
            "px-3 py-1.5 text-sm cursor-pointer outline-none "
            "transition-colors duration-100 "
            "aria-disabled:opacity-50 aria-disabled:cursor-not-allowed"
        ),
        # ``opacity-70`` (not ``text-text/70``) so the icon INHERITS the
        # row's tint : a plain row's icon dims against the body text, a
        # ``color="error"`` row's icon goes red with the label instead of
        # staying grey (a hardcoded ``text-*`` here beat the inherited tint).
        "icon_left": "shrink-0 opacity-70",
        "label": "flex-1 truncate",
        "icon_right": "shrink-0 opacity-70",
        "shortcut": (
            "shrink-0 ms-auto text-xs text-muted/70 tabular-nums"
        ),
    },
    # Per-row tint (label + hover/focus bg). ``neutral`` is the default
    # (no ``color=``) ; ``error`` paints a delete-style red row, etc. Plain
    # ``hover:`` so ``<a>`` link rows tint too.
    "colors": {
        "neutral": "hover:bg-text/[0.04] focus:bg-text/[0.04]",
        "error":   "text-error hover:bg-error/10 focus:bg-error/10",
        "warning": "text-warning hover:bg-warning/10 focus:bg-warning/10",
        "success": "text-success hover:bg-success/10 focus:bg-success/10",
    },
}
