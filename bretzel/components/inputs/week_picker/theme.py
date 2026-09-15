"""Default :class:`WeekPicker` theme.

Même silhouette que :class:`DatePicker` — un champ éditable et un bouton
icône DANS le même anneau de focus, un popover ancré dessous. Seul le
CONTENU du panneau diffère (``ui.calendar(mode="week")``), donc les
chaînes de classes sont volontairement les mêmes : deux champs de
formulaire de la même famille doivent se ressembler au pixel.

⚠️ Les chaînes restent RECOPIÉES et non partagées, à dessein — c'est la
règle du dépôt (`feedback_no_shared_style_tokens`) : on harmonise la
convention, on ne factorise pas les tokens visuels. Ce qui EST partagé,
c'est la mécanique (`inputs/_picker_field.py`).

Slots :
- ``root``          : le wrapper — porte le scope ``bz-data``
- ``input_frame``   : le champ visible (input + boutons, un seul anneau)
- ``input_field``   : l'``<input>`` typable, sans cadre propre
- ``clear_button``  : le ``×``, visible seulement s'il y a une valeur
- ``trigger_button``: le bouton calendrier qui ouvre le panneau
- ``button_icon``   : le glyphe dans les deux boutons
- ``panel``         : le popover ancré par ``$bz.helpers.floating``
"""

from __future__ import annotations

from typing import Any

WEEK_PICKER_THEME: dict[str, Any] = {
    "slots": {
        "root": "bz-week-picker relative flex flex-col w-full",
        "input_frame": (
            "flex items-stretch w-full rounded-field border-(length:--bz-stroke) border-text/10 "
            "bg-interface text-text transition-all duration-200 "
            "focus-within:border-(--bz-solid) focus-within:ring-2 "
            "focus-within:ring-(--bz-focus-soft) focus-within:ring-offset-2 "
            "focus-within:ring-offset-background "
            "has-[input:disabled]:opacity-50 "
            "has-[input:disabled]:cursor-not-allowed"
        ),
        "input_field": (
            "flex-1 min-w-0 px-3 bg-transparent text-text "
            "placeholder:text-muted/60 outline-none "
            "rounded-l-field disabled:cursor-not-allowed"
        ),
        "clear_button": (
            "shrink-0 inline-flex items-center justify-center "
            "text-muted/60 not-disabled:hover:text-text outline-none "
            "transition-colors disabled:opacity-50 "
            "disabled:cursor-not-allowed"
        ),
        "trigger_button": (
            "shrink-0 inline-flex items-center justify-center "
            "text-(--bz-text) not-disabled:hover:bg-(--bz-bg) rounded-r-field "
            "outline-none focus-visible:ring-2 focus-visible:ring-inset "
            "focus-visible:ring-(--bz-focus) transition-colors "
            "disabled:opacity-50 disabled:cursor-not-allowed"
        ),
        "button_icon": "inline-flex shrink-0 text-current",
        "panel": (
            "absolute z-40 mt-1 "
            "rounded-box border-(length:--bz-stroke) border-text/10 bg-interface shadow-lg "
            # Le fondu entrant, cadence des CHAMPS (75 ms, moitié de
            # celle des menus). Mécanisme des trois classes : un seul
            # exemplaire, dans ``overlay/dropdown/theme.py``.
            "transition-[opacity,display] transition-discrete duration-75 "
            "starting:opacity-0"
        ),
    },
    # La hauteur du palier vit sur ``input_frame`` — le cadre, qui porte la
    # bordure. En ``box-sizing: border-box``, ``h-10`` sur le cadre vaut
    # 40 px bordure comprise, comme ``ui.input`` qui pose hauteur et
    # bordure sur le MÊME élément. Posée sur l'enfant, elle donnait
    # 40 px + les 2 px du cadre : **42 px**, 2 px de plus que tout autre
    # contrôle, aux cinq paliers. Mesuré le 2026-08-23, gardé par
    # ``tests/runtime_js/test_form_controls_share_one_height.py``.
    # Les enfants n'ont donc plus de ``h-*`` : le cadre est
    # ``items-stretch``, ils remplissent sa hauteur intérieure.
    "sizes": {
        "xs": {"input_frame": "h-7", "input_field": "text-xs",
               "clear_button": "w-6", "trigger_button": "w-7",
               "button_icon": "text-xs"},
        "sm": {"input_frame": "h-8", "input_field": "text-xs",
               "clear_button": "w-7", "trigger_button": "w-8",
               "button_icon": "text-sm"},
        "md": {"input_frame": "h-10", "input_field": "text-sm",
               "clear_button": "w-8", "trigger_button": "w-10",
               "button_icon": "text-base"},
        "lg": {"input_frame": "h-12", "input_field": "text-base",
               "clear_button": "w-9", "trigger_button": "w-12",
               "button_icon": "text-lg"},
        "xl": {"input_frame": "h-14", "input_field": "text-lg",
               "clear_button": "w-10", "trigger_button": "w-14",
               "button_icon": "text-xl"},
    },
}
