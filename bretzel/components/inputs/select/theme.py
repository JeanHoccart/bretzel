"""Default :class:`Select` theme.

Custom popover-based combobox — no native ``<select>``. The trigger
is a button styled like an Input ; the panel is an absolute-
positioned dropdown of options. Keyboard navigation (↑↓ Enter
Escape) is wired client-side via the ``bz-*`` runtime.

Slots :
- ``root``      : ``relative w-full`` wrapper anchoring the panel
- ``trigger``   : the button shown when closed (border + chevron)
- ``label``     : the inner ``<span>`` showing the current value
                  or the placeholder
- ``placeholder`` : muted color modifier when no value picked
- ``chevron``   : the trailing chevron icon
- ``panel``     : the absolute dropdown holding options
- ``option``    : each option button — base + size scaling
- ``option_active`` : highlighted-state modifier (hover / keyboard)
- ``option_check``    : the ✓ marking a PICKED option (multi only) —
                 the affordance ``option_selected``'s accent alone
                 cannot carry, since ``option_active`` is accented too
- ``option_selected`` : selected-state modifier (the current value)
"""

from __future__ import annotations

from typing import Any

SELECT_THEME: dict[str, Any] = {
    "slots": {
        # Outer wrapper. ``relative`` so the panel anchors against
        # the trigger's box ; full-width by default to match other
        # form controls.
        "root": "bz-select relative w-full",
        # Trigger button — same visual as Input/Textarea so the form
        # looks coherent.
        "trigger": (
            "flex items-center w-full rounded-field border-(length:--bz-stroke) "
            "border-text/10 bg-interface text-text "
            "cursor-pointer outline-none "
            "transition-all duration-200 "
            "focus:border-(--bz-solid) "
            "focus:ring-2 focus:ring-(--bz-focus-soft) "
            "focus:ring-offset-2 focus:ring-offset-background "
            "disabled:opacity-50 disabled:cursor-not-allowed "
            "disabled:bg-muted/10"
        ),
        # Inner label ; ``truncate`` keeps long values one-line.
        "label": "flex-1 text-start truncate",
        # Modifier added when the displayed text is the placeholder.
        "placeholder": "text-muted/70",
        # Chevron icon. ``pointer-events-none`` so clicks pass through
        # to the trigger button underneath.
        "chevron": (
            "shrink-0 ml-2 text-muted pointer-events-none "
            "transition-transform duration-200"
        ),
        # Dropdown panel — Card-style surface. Positioned by
        # ``$bz.helpers.floating`` (``position: fixed`` + inline
        # ``top``/``left``), which pins ``min-width`` to the trigger via
        # ``match_width``. NO ``left-0 right-0`` here : under fixed
        # positioning the leftover ``right: 0`` stretches the panel to the
        # viewport's right edge (cf. traps.md § "panel left-0 right-0
        # under floating").
        "panel": (
            "absolute z-40 mt-1 overflow-y-auto "
            "rounded-box border-(length:--bz-stroke) border-text/10 bg-interface "
            "shadow-lg "
            # Le fondu entrant, à la cadence des CHAMPS — moitié de
            # celle des menus. Le mécanisme des trois classes est
            # expliqué en un seul exemplaire dans
            # ``overlay/dropdown/theme.py``.
            #
            # Pourquoi 75 et pas 150 : un menu est un DÉTOUR (on
            # l'ouvre, on regarde, on choisit) et 150 ms s'y lisent
            # comme du soin ; un champ est sur le CHEMIN, souvent
            # rempli à la chaîne, et la même durée s'y lit comme de
            # la latence. Rapporté à l'usage le 2026-09-04, sur les
            # deux à la fois — donc c'est bien la CLASSE de
            # composant qui décide, pas le composant.
            "transition-[opacity,display] transition-discrete duration-75 "
            "starting:opacity-0"
        ),
        # Each option — full-width clickable row.
        "option": (
            "flex items-center w-full text-start "
            "px-3 py-2 cursor-pointer outline-none "
            "transition-colors duration-100 "
            "disabled:opacity-50 disabled:cursor-not-allowed"
        ),
        # Highlighted state — applied via ``bz-attr:class`` when
        # the keyboard cursor or hover lands on the option.
        "option_active": "bg-(--bz-bg) text-(--bz-text)",
        # La coche d'une option prise (mode multi). ``ml-auto`` la pousse
        # au bord droit sans toucher l'alignement du libellé. La taille du
        # glyphe vit dans ``sizes[<size>]["check_icon_size"]`` — une icône
        # se taille en ``text-*``, jamais en ``w-``/``h-`` (traps.md).
        "option_check": "shrink-0 ms-auto text-(--bz-text)",
        # Selected state — applied to the option whose value matches
        # the current binding.
        "option_selected": "font-semibold text-(--bz-text)",
        # ── Multi-mode additions ─────────────────────────────────────
        # Mirror the slots Combobox carries for the same purpose
        # (pills + header bar). Identical recipes so a form mixing
        # Select-multi + Combobox-multi reads as one family —
        # duplication is intentional pre-extraction (cf.
        # components-roadmap.md).
        # No pill classes here : multi-mode pills source their styling
        # from :data:`BADGE_THEME` via ``_badge_pill_classes()`` in
        # ``combobox.combobox`` — single source of truth across pickers.
        # Pills row INSIDE the trigger — used in multi mode CLOSED
        # state. ``flex-1 min-w-0`` so pills wrap correctly while
        # keeping the chevron + clear button to the right.
        "pills_row": (
            "flex flex-wrap items-center gap-1 flex-1 min-w-0"
        ),
        # Unified header bar at the top of the panel : counter +
        # pills + bulk actions. Sticky so it survives scroll.
        "header_bar": (
            "flex flex-wrap items-center gap-2 px-2 py-1.5 "
            "border-b-(length:--bz-stroke) border-text/10 sticky top-0 "
            "bg-interface/95 backdrop-blur z-10"
        ),
        # Taille de texte dans ``sizes[<size>]["header_counter"]`` — ne PAS
        # la remettre ici (slot + table = collision Tailwind, traps.md).
        "header_counter": (
            "shrink-0 text-muted tabular-nums"
        ),
        "header_pills": (
            "flex flex-wrap items-center gap-1 flex-1 min-w-0"
        ),
        "header_actions": (
            "shrink-0 inline-flex items-center gap-1 ms-auto"
        ),
        "header_btn_primary": (
            "inline-flex items-center px-2 py-1 rounded-selector "
            "font-medium text-(--bz-text) "
            "not-disabled:hover:bg-(--bz-bg) cursor-pointer "
            "outline-none focus-visible:ring-2 "
            "focus-visible:ring-(--bz-focus) "
            "disabled:opacity-50 disabled:cursor-not-allowed"
        ),
        "header_btn_muted": (
            "inline-flex items-center px-2 py-1 rounded-selector "
            "font-medium text-muted "
            "not-disabled:hover:bg-error/10 not-disabled:hover:text-error "
            "cursor-pointer outline-none focus-visible:ring-2 "
            "focus-visible:ring-error/40 "
            "disabled:opacity-50 disabled:cursor-not-allowed"
        ),
        # Clear-all × on the trigger right edge (multi mode). Hover
        # gated on ``not-disabled:`` so the × stays visually frozen when
        # the parent Select is ``disabled`` — cf. traps.md § "hover:
        # sur un control disabled".
        "clear": (
            "shrink-0 inline-flex items-center justify-center "
            "ml-1 rounded-selector text-muted not-disabled:hover:text-text "
            "not-disabled:hover:bg-text/5 cursor-pointer outline-none "
            "focus-visible:ring-2 focus-visible:ring-(--bz-focus)"
        ),
    },
    # Échelle alignée sur ``COMBOBOX_THEME["sizes"]`` : Select-multi et
    # Combobox-multi doivent se lire comme une seule famille dans un même
    # formulaire. Ils partagent déjà ``_badge_pill_classes`` ; toute
    # retouche ici va en paire.
    #
    # ⚠️ « Alignée », PAS « identique » — le commentaire disait « mêmes
    # clés, mêmes tokens », ce qui est faux et empêchait toute gate de
    # s'appuyer dessus (mesuré 2026-07-28). Trois écarts sont
    # STRUCTURELS : combobox porte ``input`` et ``empty`` que select n'a
    # pas (pas de filtre client → jamais d'état « aucun résultat »), et
    # son ``trigger`` utilise ``min-h-[2.5rem]`` là où select fige
    # ``h-10`` — même hauteur, exprimée autrement parce que le trigger du
    # combobox grandit avec ses pills.
    #
    # Ce qui EST gardé mécaniquement, c'est l'apparence du panneau
    # (ombre / décalage / rayon), cf.
    # ``tests/consistency/test_anchored_panels_match.py``.
    #
    # Les clés en ``*_size`` ne sont pas des classes mais les tokens de
    # taille des sous-composants (Badge, Icon) — convention ``BADGE_THEME``.
    # Une icône se taille en ``text-*``, jamais en ``w-``/``h-`` (traps.md).
    #
    # ``md`` = l'apparence historique, inchangée.
    "sizes": {
        "xs": {
            "trigger": "h-7 px-2 text-xs",
            "option": "text-xs",
            "check_icon_size": "xs",
            "panel": "max-h-48",
            "header_counter": "text-[10px]",
            "header_btn_primary": "text-[10px]",
            "header_btn_muted": "text-[10px]",
            "pill_size": "xs",
            "chevron_size": "xs",
            "clear_icon_size": "xs",
        },
        "sm": {
            "trigger": "h-8 px-3 text-xs",
            "option": "text-xs",
            "check_icon_size": "xs",
            "panel": "max-h-52",
            "header_counter": "text-xs",
            "header_btn_primary": "text-xs",
            "header_btn_muted": "text-xs",
            "pill_size": "xs",
            "chevron_size": "xs",
            "clear_icon_size": "xs",
        },
        "md": {
            "trigger": "h-10 px-3 text-sm",
            "option": "text-sm",
            "check_icon_size": "sm",
            "panel": "max-h-60",
            "header_counter": "text-xs",
            "header_btn_primary": "text-xs",
            "header_btn_muted": "text-xs",
            "pill_size": "sm",
            "chevron_size": "sm",
            "clear_icon_size": "xs",
        },
        "lg": {
            "trigger": "h-12 px-4 text-base",
            "option": "text-base",
            "check_icon_size": "md",
            "panel": "max-h-72",
            "header_counter": "text-sm",
            "header_btn_primary": "text-sm",
            "header_btn_muted": "text-sm",
            "pill_size": "md",
            "chevron_size": "md",
            "clear_icon_size": "sm",
        },
        "xl": {
            "trigger": "h-14 px-5 text-lg",
            "option": "text-lg",
            "check_icon_size": "lg",
            "panel": "max-h-80",
            "header_counter": "text-base",
            "header_btn_primary": "text-base",
            "header_btn_muted": "text-base",
            "pill_size": "lg",
            "chevron_size": "lg",
            "clear_icon_size": "sm",
        },
    },
}
