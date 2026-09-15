"""Default :class:`Tooltip` theme.

Tiny floating panel : color-driven surface (defaults to the V1 dark
"text" surface for the neutral case ; semantic colors swap to a
matching tinted background for warning / error / etc.). Soft shadow,
small text. Arrow is a 8x8 rotated square positioned by the active
side, picks up the same color so it visually merges.

Slots :
- ``root``  : ``inline-block w-fit h-fit`` (PAS ``relative`` : le panneau est téléporté et positionné en ``fixed`` par ``$bz.helpers.floating``, donc la root n'a pas besoin d'être un contexte de positionnement — et le ``w-fit h-fit`` l'empêche d'être étirée par un vstack ``items-stretch``) wrapper that hosts the
              trigger + the hidden tooltip panel
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
        # — cf. traps.md § "Root inline-flex étirée par un parent
        # flex/grid items-stretch". When the trigger is ``w-full``, the
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
            # Le fondu entrant, court. Le mécanisme des trois
            # classes est expliqué en un seul exemplaire dans
            # ``overlay/dropdown/theme.py``.
            #
            # ⚠️ Le tooltip est le SEUL de la famille à payer deux
            # attentes qui s'ajoutent : son délai d'ouverture, PUIS
            # le fondu. À 300 + 150 il fallait presque une demi-
            # seconde avant de pouvoir lire — signalé à l'usage le
            # 2026-09-04. Les deux ont été coupés de moitié (le
            # délai vit dans ``tooltip.py``), donc 150 + 75.
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
        # ⚠️ **Et son OFFSET vient du helper, pas de ``left-1/2``.** Le
        # côté suivait déjà le retournement ; la position le long de ce
        # côté, non. Le helper recadre le panneau contre le bord de
        # l'écran, et une flèche posée au milieu de la bulle pointe alors
        # à côté de son déclencheur — 25 px d'écart mesurés le 2026-09-09
        # sur un bouton collé au bord droit. ``--bz-arrow`` porte la
        # position de l'ancre DANS le panneau ; le défaut ``50%`` vit sur
        # le slot ``panel``, pour que le rendu serveur (avant que le
        # helper ait tourné) reste centré.
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
