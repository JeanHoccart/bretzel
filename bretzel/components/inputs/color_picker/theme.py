"""Default :class:`ColorPicker` theme.

Silhouette de la famille picker — un cadre bordé qui porte la hauteur du
palier, un champ éditable dedans, un bouton déclencheur à droite, un
panneau ancré. La seule différence est le contenu du panneau : une
grille de pastilles au lieu d'une grille de jours.

⚠️ **La hauteur du palier est sur le CADRE**, qui porte la bordure. La
poser sur l'``<input>`` intérieur rend 2 px de plus (``box-sizing:
border-box`` compte la bordure), et l'écart ne se voit qu'à l'écran —
cf. ``traps.md`` § *Hauteur de palier sur l'ENFANT*.

La pastille de tête n'est pas décorative : c'est le seul endroit où la
valeur se lit **comme une couleur**. Un hexadécimal ne se relit pas.
"""

from __future__ import annotations

from typing import Any

COLOR_PICKER_THEME: dict[str, Any] = {
    "slots": {
        "root": "bz-color-picker relative flex flex-col w-full",
        "input_frame": (
            "flex items-center gap-2 w-full rounded-field border-(length:--bz-stroke) "
            "border-text/15 bg-interface transition-colors "
            "focus-within:border-(--bz-solid) "
            "focus-within:ring-2 focus-within:ring-(--bz-focus-soft) "
            "focus-within:ring-offset-2 focus-within:ring-offset-background "
            "has-[:disabled]:opacity-50 has-[:disabled]:cursor-not-allowed"
        ),
        # La pastille de tête — elle REND la valeur courante.
        #
        # ⚠️ ``bg-text/5`` et pas un damier : la première écriture était
        # un ``repeating-conic-gradient`` coupé en DEUX littéraux Python
        # pour tenir dans la ligne, et le compilateur Tailwind scanne les
        # sources — il n'aurait vu ni l'une ni l'autre moitié. Classe
        # inexistante en prod, damier correct en dev. Attrapé par
        # ``test_emitted_classes_exist_in_source`` avant de partir.
        #
        # Le gris de repos joue le même rôle : une pastille SANS couleur
        # ne se confond pas avec une pastille blanche.
        "swatch": (
            "shrink-0 rounded-selector border-(length:--bz-stroke) border-text/15 bg-text/5"
        ),
        "input_field": (
            "flex-1 min-w-0 bg-transparent outline-none font-mono "
            "text-text placeholder:text-muted/70 "
            "disabled:cursor-not-allowed"
        ),
        "clear_button": (
            "shrink-0 inline-flex items-center justify-center rounded-selector "
            "text-muted hover:text-text transition-colors cursor-pointer "
            "outline-none focus-visible:ring-2 "
            "focus-visible:ring-(--bz-focus) "
            "disabled:cursor-not-allowed"
        ),
        "trigger_button": (
            "shrink-0 inline-flex items-center justify-center rounded-selector "
            "text-muted hover:text-text transition-colors cursor-pointer "
            "outline-none focus-visible:ring-2 "
            "focus-visible:ring-(--bz-focus) "
            "disabled:cursor-not-allowed"
        ),
        "button_icon": "",
        "panel": (
            "absolute z-50 mt-1 rounded-box border-(length:--bz-stroke) border-text/10 "
            "bg-surface shadow-lg p-3 w-max max-w-[min(20rem,100vw-2rem)] "
            # Le fondu entrant, cadence des CHAMPS (75 ms, moitié de
            # celle des menus). Mécanisme des trois classes : un seul
            # exemplaire, dans ``overlay/dropdown/theme.py``.
            "transition-[opacity,display] transition-discrete duration-75 "
            "starting:opacity-0"
        ),
        "grid": "grid grid-cols-8 gap-1.5",
        # Une pastille du panneau. ``data-selected`` marque celle qui vaut
        # la valeur courante — l'anneau la désigne sans changer sa taille,
        # donc la grille ne bouge pas quand la sélection change.
        "swatch_cell": (
            "h-6 w-6 rounded-selector border-(length:--bz-stroke) border-text/15 cursor-pointer "
            "transition-transform hover:scale-110 "
            "outline-none focus-visible:ring-2 "
            "focus-visible:ring-(--bz-focus) focus-visible:ring-offset-1 "
            "focus-visible:ring-offset-surface "
            "data-[selected=true]:ring-2 "
            "data-[selected=true]:ring-(--bz-solid) "
            "data-[selected=true]:ring-offset-2 "
            "data-[selected=true]:ring-offset-surface"
        ),
        "panel_label": "text-xs text-muted mb-2 font-medium",
    },
    # ``sizes[<palier>][<slot>]`` — la forme CANONIQUE. Les trois
    # pickers de date l'écrivent inversée et sont des exceptions
    # déclarées ; un composant neuf n'a aucune raison de les imiter là.
    #
    # L'échelle est celle des contrôles — ``h-7/h-8/h-10/h-12/h-14``, la
    # même qu'Input et Select. Un palier manquant ne lève pas : le render
    # retombe sur ``md``, donc le champ sort plus petit que son voisin au
    # même palier, et ça ne se voit qu'à l'écran.
    "sizes": {
        "xs": {
            "input_frame": "h-7 px-1.5", "swatch": "h-4 w-4",
            "input_field": "text-xs", "clear_button": "h-4 w-4",
            "trigger_button": "h-4 w-4", "button_icon": "xs",
        },
        "sm": {
            "input_frame": "h-8 px-2", "swatch": "h-5 w-5",
            "input_field": "text-xs", "clear_button": "h-5 w-5",
            "trigger_button": "h-5 w-5", "button_icon": "sm",
        },
        "md": {
            "input_frame": "h-10 px-2.5", "swatch": "h-6 w-6",
            "input_field": "text-sm", "clear_button": "h-6 w-6",
            "trigger_button": "h-6 w-6", "button_icon": "md",
        },
        "lg": {
            "input_frame": "h-12 px-3", "swatch": "h-7 w-7",
            "input_field": "text-base", "clear_button": "h-7 w-7",
            "trigger_button": "h-7 w-7", "button_icon": "md",
        },
        "xl": {
            "input_frame": "h-14 px-3.5", "swatch": "h-8 w-8",
            "input_field": "text-lg", "clear_button": "h-8 w-8",
            "trigger_button": "h-8 w-8", "button_icon": "lg",
        },
    },
}
