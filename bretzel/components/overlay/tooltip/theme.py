"""Default :class:`Tooltip` theme.

Tiny floating panel : color-driven surface (defaults to the V1 dark
"text" surface for the neutral case ; semantic colors swap to a
matching tinted background for warning / error / etc.). Soft shadow,
small text. Arrow is a 8x8 rotated square positioned by the active
side, picks up the same color so it visually merges.

Slots :
- ``root``  : ``inline-block w-fit h-fit`` (NOT ``relative``: the panel
              is teleported and positioned ``fixed`` by
              ``$bz.helpers.floating``, so the root does not need to be a
              positioning context — and the ``w-fit h-fit`` stops it
              being stretched by an ``items-stretch`` vstack) wrapper
              that hosts the trigger + the hidden tooltip panel
- ``panel`` : the tooltip itself, absolute-positioned by side
- ``arrow`` : rotated triangle pointing at the trigger (always present)
"""

from __future__ import annotations

from typing import Any

TOOLTIP_THEME: dict[str, Any] = {
    "slots": {
        # ``inline-block w-fit h-fit`` : the wrapper hosts the trigger
        # and acts as the bounding-rect reference for positioning. The
        # ``w-fit h-fit`` is critical : without it, a vstack / grid
        # parent with the default ``items-stretch`` STRETCHES the
        # ``inline-block`` to 100% of the cross-axis, so the floating
        # helper reads a stretched rect and centers the panel on the row
        # width instead of the trigger. Same fix Popover + Dropdown carry
        # — cf. traps.md § "An inline-flex root stretched by a flex/grid
        # items-stretch parent". When the trigger is ``w-full``, the
        # renderer swaps both ``inline-block`` and ``w-fit``/``h-fit`` for
        # ``block w-full`` (see ``trigger_is_full_width``).
        "root": "inline-block w-fit h-fit",
        # ``fixed`` (set by the renderer — Bretzel replaces ``absolute``
        # at compose time). ``--bz-solid`` carries the surface tint
        # for the configured color (default ``text`` → neutral dark).
        # ``max-w-xs`` + wrapping : a long tip wraps inside a sane width
        # instead of forcing ONE line that runs off the viewport.
        # ``break-words`` handles an unbroken long token.
        "panel": (
            "absolute z-40 px-2.5 py-1.5 rounded-box "
            "text-xs font-medium leading-tight "
            "bg-(--bz-solid) text-(--bz-on-solid) shadow-md "
            "max-w-xs break-words pointer-events-none "
            # The enter fade, short. The mechanism of the three classes
            # is explained in a single copy in
            # ``overlay/dropdown/theme.py``.
            #
            # ⚠️ The tooltip is the family's ONLY member to pay two waits
            # that add up: its opening delay, THEN the fade. At 300 + 150
            # it took almost half a second before you could read —
            # reported from use on 2026-09-04. Both were halved (the
            # delay lives in ``tooltip.py``), so 150 + 75.
            "transition-[opacity,display] transition-discrete duration-75 "
            "starting:opacity-0 [--bz-arrow:50%]"
        ),
        # Arrow is absolute-positioned RELATIVE TO THE PANEL (it stays
        # inside the panel after the teleport). Its anchor follows the
        # side ``$bz.helpers.floating`` actually resolved at runtime :
        # the helper writes ``data-side`` on the panel, and the panel is
        # a ``group`` — so the arrow keys off ``group-data-[side=…]``.
        # All four sides are present ; only the matching one applies.
        #
        # ⚠️ **And its OFFSET comes from the helper, not from
        # ``left-1/2``.** The side already followed the flip; the
        # position along that side did not. The helper reframes the panel
        # against the screen's edge, and an arrow placed in the middle of
        # the bubble then points beside its trigger — 25 px of gap
        # measured on 2026-09-09 on a button flush with the right edge.
        # ``--bz-arrow`` carries the anchor's position INSIDE the panel;
        # the ``50%`` default lives on the ``panel`` slot, so the server
        # render (before the helper has run) stays centred.
        "arrow": (
            "absolute h-2 w-2 rotate-45 bg-(--bz-solid) "
            "group-data-[side=top]:top-full "
            "group-data-[side=top]:start-(--bz-arrow) "
            "group-data-[side=top]:-translate-x-1/2 "
            "group-data-[side=top]:-mt-1 "
            "group-data-[side=bottom]:bottom-full "
            "group-data-[side=bottom]:start-(--bz-arrow) "
            "group-data-[side=bottom]:-translate-x-1/2 "
            "group-data-[side=bottom]:-mb-1 "
            "group-data-[side=left]:left-full "
            "group-data-[side=left]:top-(--bz-arrow) "
            "group-data-[side=left]:-translate-y-1/2 "
            "group-data-[side=left]:-ml-1 "
            "group-data-[side=right]:right-full "
            "group-data-[side=right]:top-(--bz-arrow) "
            "group-data-[side=right]:-translate-y-1/2 "
            "group-data-[side=right]:-mr-1"
        ),
    },
}
