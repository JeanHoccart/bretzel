"""Default :class:`TimePicker` theme.

Même silhouette que :class:`DatePicker` — un champ éditable et un bouton
icône DANS le même anneau de focus, un popover ancré dessous — mais le
panneau n'est pas une grille : ce sont **deux colonnes aimantées**,
heures et minutes.

Pourquoi des colonnes maison et pas un ``<input type="time">`` : un
widget natif n'est pas thématisable et change complètement d'allure entre
Chrome, Safari et Android. C'est la leçon payée sur la scrollbar du
Carousel, en plus visible.

Les colonnes réutilisent deux mécaniques déjà écrites :

- ``bz-no-scrollbar`` (hook du CSS framework, ``theme/css.py``) — une
  colonne de 24 heures défile, et sa barre native serait le seul élément
  non thématisé du composant ;
- ``snap-y snap-mandatory`` + ``snap-center`` — le même aimantage CSS que
  la piste du Carousel, pour que le défilement s'arrête sur une valeur
  et jamais entre deux.

Slots :
- ``root``          : le wrapper — porte le scope ``bz-data``
- ``input_frame``   : le champ visible (input + boutons, un seul anneau)
- ``input_field``   : l'``<input>`` typable, sans cadre propre
- ``clear_button``  : le ``×``, visible seulement s'il y a une valeur
- ``trigger_button``: le bouton horloge qui ouvre le panneau
- ``button_icon``   : le glyphe dans les deux boutons
- ``panel``         : le popover ancré par ``$bz.helpers.floating``
- ``columns``       : la rangée des deux colonnes
- ``column``        : une colonne défilante aimantée
- ``cell``          : une cellule d'heure ou de minute
- ``column_label``  : l'entête « Heures » / « Minutes »
"""

from __future__ import annotations

from typing import Any

TIME_PICKER_THEME: dict[str, Any] = {
    "slots": {
        # ``w-full`` et pas ``w-fit`` : le champ remplit son parent comme
        # tout autre input de formulaire, donc il s'aligne sur ses
        # voisins dans une grille et ne déborde jamais de sa cellule
        # (le défaut mesuré sur date_picker avant sa correction).
        "root": "bz-time-picker relative flex flex-col w-full",
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
        # Positionné par ``$bz.helpers.floating`` (``position: fixed`` +
        # coordonnées inline). PAS de ``left-0`` / ``right-0`` : sous
        # position fixe ils se battent avec les coordonnées inline (cf.
        # traps.md § « panel left-0 right-0 under floating »).
        "panel": (
            "absolute z-40 mt-1 p-2 "
            "rounded-box border-(length:--bz-stroke) border-text/10 bg-interface shadow-lg "
            # Le fondu entrant, cadence des CHAMPS (75 ms, moitié de
            # celle des menus). Mécanisme des trois classes : un seul
            # exemplaire, dans ``overlay/dropdown/theme.py``.
            "transition-[opacity,display] transition-discrete duration-75 "
            "starting:opacity-0"
        ),
        "columns": "flex gap-1",
        # ``bz-no-scrollbar`` : hook du CSS framework, pas un utilitaire
        # Tailwind — les variantes arbitraires équivalentes ne compilent
        # pas (mesuré sur le Carousel).
        "column": (
            "bz-no-scrollbar flex flex-col gap-0.5 overflow-y-auto "
            "snap-y snap-mandatory scroll-pt-1"
        ),
        "column_label": (
            "sticky top-0 z-10 bg-interface text-muted font-medium "
            "text-center pb-1"
        ),
        "cell": (
            "snap-center shrink-0 rounded-selector text-center tabular-nums "
            "cursor-pointer transition-colors duration-150 "
            "not-disabled:hover:bg-(--bz-bg) "
            "focus-visible:outline-none focus-visible:ring-2 "
            "focus-visible:ring-inset focus-visible:ring-(--bz-focus) "
            "data-[selected=true]:bg-(--bz-solid) "
            "data-[selected=true]:text-(--bz-on-solid) "
            "data-[selected=true]:font-semibold "
            "disabled:opacity-40 disabled:cursor-not-allowed "
            "disabled:hover:bg-transparent"
        ),
    },
    # La hauteur du palier vit sur ``input_frame`` — le cadre, qui porte
    # la bordure. En ``box-sizing: border-box``, ``h-10`` sur le cadre
    # vaut 40 px bordure comprise, comme ``ui.input`` qui pose hauteur et
    # bordure sur le MÊME élément. Posée sur l'enfant, elle donnait
    # 40 px + les 2 px du cadre : **42 px**, 2 px de plus que tout autre
    # contrôle, aux cinq paliers. Mesuré le 2026-08-23, gardé par
    # ``tests/runtime_js/test_form_controls_share_one_height.py``.
    # Les enfants n'ont donc plus de ``h-*`` : le cadre est
    # ``items-stretch``, ils remplissent sa hauteur intérieure.
    "sizes": {
        "xs": {
            "input_frame": "h-7",
            "input_field": "text-xs",
            "clear_button": "w-6",
            "trigger_button": "w-7",
            "button_icon": "text-xs",
            "column": "max-h-40 w-12",
            "column_label": "text-[10px]",
            "cell": "py-0.5 text-xs",
        },
        "sm": {
            "input_frame": "h-8",
            "input_field": "text-xs",
            "clear_button": "w-7",
            "trigger_button": "w-8",
            "button_icon": "text-sm",
            "column": "max-h-44 w-14",
            "column_label": "text-[10px]",
            "cell": "py-1 text-xs",
        },
        "md": {
            "input_frame": "h-10",
            "input_field": "text-sm",
            "clear_button": "w-8",
            "trigger_button": "w-10",
            "button_icon": "text-base",
            "column": "max-h-56 w-16",
            "column_label": "text-xs",
            "cell": "py-1.5 text-sm",
        },
        "lg": {
            "input_frame": "h-12",
            "input_field": "text-base",
            "clear_button": "w-9",
            "trigger_button": "w-12",
            "button_icon": "text-lg",
            "column": "max-h-64 w-20",
            "column_label": "text-sm",
            "cell": "py-2 text-base",
        },
        "xl": {
            "input_frame": "h-14",
            "input_field": "text-lg",
            "clear_button": "w-10",
            "trigger_button": "w-14",
            "button_icon": "text-xl",
            "column": "max-h-72 w-24",
            "column_label": "text-base",
            "cell": "py-2.5 text-lg",
        },
    },
}
