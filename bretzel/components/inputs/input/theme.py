"""Default :class:`Input` theme.

Identity : soft border ``border-text/10``, generous ``rounded-field``,
focus ring tinted ``ring-(--bz-focus-soft)`` over the page
``ring-offset-background``, ``transition-all duration-200`` so the
focus state slides in instead of snapping.

Two roots — the input has TWO architectures depending on whether the
caller passed prefix / suffix slots :

- **No affixes** (the common case) : ``root`` is a thin relative
  wrapper, the focus ring lives on the ``<input>`` itself
  (``input`` slot).
- **With prefix or suffix** : the caller wires
  ``ui.input(prefix="$", ...)`` ; render switches to the ``prefix_root``
  layout where the frame and the focus ring live on the WRAPPER, and
  the ``<input>`` itself goes transparent (``input_inner`` slot).

Slot ``clear_button`` : le ``×`` de ``clearable=True``, même bord droit
que ``icon_right``.

Icon slots ``icon_left`` / ``icon_right`` overlay the input absolute-
positioned and shift their colour on ``group-focus-within`` so the
icon "lights up" in the colour as the field gets focus.
"""

from __future__ import annotations

from typing import Any

INPUT_THEME: dict[str, Any] = {
    "slots": {
        # No-affix architecture : root just positions icons over the input.
        # ``transition`` (not ``transition-all``) so colours / ring / shadow
        # fade smoothly but WIDTH / HEIGHT / PADDING never animate — those
        # would otherwise play a visible grow→shrink when the browser
        # applies styles late (dev browser-Tailwind) or idiomorph swaps the
        # node on boosted nav.
        "root": (
            "relative flex items-center w-full transition "
            "duration-200 group"
        ),
        # The visible <input> in the no-affix case — frame + focus ring live here.
        "input": (
            "bz-input "  # audit marker — cf. tests/audit/checklist.py
            "block w-full rounded-field border-(length:--bz-stroke) border-text/10 "
            "bg-interface text-text placeholder:text-muted/60 "
            "outline-none transition duration-200 "
            "focus:border-(--bz-solid) "
            "focus:ring-2 focus:ring-(--bz-focus-soft) "
            "focus:ring-offset-2 focus:ring-offset-background "
            "disabled:opacity-50 disabled:cursor-not-allowed "
            "disabled:bg-muted/10 "
            "read-only:cursor-default read-only:bg-interface/50"
        ),
        # Affixes architecture : the wrapper carries the frame + ring.
        # ``relative`` : le ``×`` de ``clearable=True`` se positionne en
        # ``absolute right-3`` comme dans l'autre disposition — une SEULE
        # écriture du slot pour les deux. Sans ancre ici, il irait se
        # caler sur le premier ancêtre positionné, c'est-à-dire n'importe
        # où dans la page.
        "prefix_root": (
            "relative flex items-center w-full rounded-field "
            "border-(length:--bz-stroke) border-text/10 "
            "bg-interface transition duration-200 group "
            "focus-within:border-(--bz-solid) "
            "focus-within:ring-2 focus-within:ring-(--bz-focus-soft) "
            "focus-within:ring-offset-2 focus-within:ring-offset-background"
        ),
        # The <input> when wrapped in prefix_root : strip its own frame.
        "input_inner": (
            "block w-full outline-none bg-transparent text-text "
            "placeholder:text-muted/60 rounded-field"
        ),
        # Inline static label slots (e.g. ``https://`` / ``.com``).
        "prefix": (
            "shrink-0 text-muted/60 text-sm font-medium select-none "
            "pl-3 py-2"
        ),
        "suffix": (
            "shrink-0 text-muted/60 text-sm font-medium select-none "
            "pr-3 py-2"
        ),
        # Absolute-positioned icons overlaid on the no-affix input ;
        # ``group-focus-within`` lights them up in the focus colour.
        "icon_left": (
            "absolute left-3 text-muted/60 "
            "group-focus-within:text-(--bz-text-muted) "
            "transition-colors pointer-events-none "
            "flex items-center justify-center"
        ),
        "icon_right": (
            "absolute right-3 text-muted/60 "
            "group-focus-within:text-(--bz-text-muted) "
            "transition-colors pointer-events-none "
            "flex items-center justify-center"
        ),
        # Le ``×`` de ``clearable=True``. Il occupe le MÊME bord droit que
        # ``icon_right`` (et que ``suffix`` dans l'autre disposition) —
        # les deux ensemble se superposeraient, et c'est à l'appelant de
        # choisir lequel il veut là.
        #
        # ``peer-placeholder-shown:hidden`` : la visibilité est du CSS
        # PUR, sans scope ni JS. ``:placeholder-shown`` matche exactement
        # quand le champ est vide, donc la croix n'existe que lorsqu'il y
        # a quelque chose à effacer, et elle réagit à la frappe sans
        # qu'aucun signal ne soit impliqué. C'est ce qui permet d'ajouter
        # l'affordance SANS toucher au scope de valeur qui vit sur
        # l'``<input>`` (et qui y vit pour une raison : son ``bz-id``
        # stable fait survivre le texte tapé à un morph).
        #
        # PAS ``pointer-events-none`` contrairement aux deux icônes : lui
        # se clique.
        "clear_button": (
            "absolute right-3 text-muted/60 "
            "not-disabled:hover:text-text cursor-pointer "
            "transition-colors outline-none rounded-selector "
            "focus-visible:ring-2 focus-visible:ring-(--bz-focus) "
            "flex items-center justify-center "
            "peer-placeholder-shown:hidden "
            "disabled:opacity-50 disabled:cursor-not-allowed"
        ),
    },
    # Sizes apply to the input ``height + padding + text-size`` and add
    # extra left/right padding when an icon slot is present (so the
    # text doesn't collide with the absolute-positioned icon).
    "sizes": {
        "xs": {
            "input": "h-7 px-2 text-xs",
            "icon_pad_left": "pl-7",
            "icon_pad_right": "pr-7",
            "clear_icon_size": "xs",
        },
        "sm": {
            "input": "h-8 px-3 text-xs",
            "icon_pad_left": "pl-8",
            "icon_pad_right": "pr-8",
            "clear_icon_size": "xs",
        },
        "md": {
            "input": "h-10 px-3 text-sm",
            "icon_pad_left": "pl-10",
            "icon_pad_right": "pr-10",
            "clear_icon_size": "sm",
        },
        "lg": {
            "input": "h-12 px-4 text-base",
            "icon_pad_left": "pl-12",
            "icon_pad_right": "pr-12",
            "clear_icon_size": "sm",
        },
        "xl": {
            "input": "h-14 px-5 text-lg",
            "icon_pad_left": "pl-14",
            "icon_pad_right": "pr-14",
            "clear_icon_size": "md",
        },
    },
}
