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
- ``check``     : the check mark of a ``checked=`` row
- ``shortcut``  : muted keyboard-shortcut hint at the right edge
"""

from __future__ import annotations

from typing import Any

DROPDOWN_THEME: dict[str, Any] = {
    "slots": {
        "root": "relative inline-flex w-fit h-fit",
        # ``min-w-[12rem]`` so the panel doesn't squish to its
        # narrowest item.
        #
        # NO vertical padding, and ``overflow-hidden``: a hovered row
        # fills the panel to its edge, its corners cut by the panel's
        # rounding — as the select's and the combobox's options do. A
        # ``py-1`` that kept the hover off the corners would leave a band
        # of panel above the first row and below the last, which reads as
        # a hover that falls short. Guarded by
        # ``tests/runtime_js/test_a_menu_row_fills_its_panel.py``.
        "panel": (
            "absolute z-40 min-w-[12rem] overflow-hidden "
            "rounded-box border-(length:--bz-stroke) border-text/10 bg-surface "
            "shadow-lg "
            # THE ENTER FADE OF AN ANCHORED PANEL — the family's
            # reference; the other panels point here.
            #
            # The runtime opens a panel by writing ``style.display``
            # inline. ``starting:opacity-0`` (``@starting-style``) is
            # what makes the entry fade: it applies to any element
            # leaving ``display:none``. Without it, nothing to start
            # from: ``transition-opacity`` alone stays at constant opacity.
            #
            # AN INSTANT EXIT, and it is the point. No ``display`` in the
            # transition list and no ``transition-discrete``: the entry
            # does not need them, and they would hold ``display`` for the
            # whole duration on CLOSING, with no fade — the opacity has
            # no closed state, so a menu would stay frozen at full opacity
            # after Escape. A leaving fade would need a closed state in
            # CSS (a mirrored ``data-open``, as ``dialog``'s), and a menu
            # that lingers reads as latency, not as care.
            #
            # Guarded by ``test_a_declared_transition_can_animate``
            # (classes) and ``tests/runtime_js/test_a_panel_closes_at_once.py``
            # (measured).
            "transition-opacity duration-150 "
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
            "group flex items-center gap-2 w-full text-start "
            "px-3 py-1.5 text-sm cursor-pointer outline-none "
            # No fade: a row lights at once and goes out at once — sliding
            # down a list, the previous row would trail behind the
            # pointer. As in a native menu.
            "aria-disabled:opacity-50 aria-disabled:cursor-not-allowed"
        ),
        # ``opacity-70`` (not ``text-text/70``) so the icon INHERITS the
        # row's tint : a plain row's icon dims against the body text, a
        # ``color="error"`` row's icon goes red with the label instead of
        # staying grey (a hardcoded ``text-*`` here beat the inherited tint).
        "icon_left": "shrink-0 opacity-70",
        "label": "flex-1 truncate",
        "icon_right": "shrink-0 opacity-70",
        # The mark of a ``checked=`` row: always there, shown on the
        # chosen one (``aria-checked="true"``, fixed or bound), so the
        # labels of a choice menu line up.
        "check": "shrink-0 invisible group-aria-checked:visible",
        "shortcut": (
            "shrink-0 ms-auto text-xs text-muted/70 tabular-nums"
        ),
    },
    # Per-row tint (label + hover/focus bg). ``neutral`` is the default
    # (no ``color=``) ; ``error`` paints a delete-style red row, etc. Plain
    # ``hover:`` so ``<a>`` link rows tint too.
    "colors": {
        "neutral": "hover:bg-interface focus:bg-interface",
        "error":   "text-error hover:bg-error/10 focus:bg-error/10",
        "warning": "text-warning hover:bg-warning/10 focus:bg-warning/10",
        "success": "text-success hover:bg-success/10 focus:bg-success/10",
    },
}
