"""Default :class:`Combobox` theme.

Search-as-you-type combobox built on a focusable text input + a
popover panel of filtered options. Single (one value) or multiple
(list of values rendered as removable pills inside the trigger).

The visual identity tracks Select / Input so a form mixing the
three reads as a single family — same border / radius / focus ring
recipe, same size scale.

Slots :
- ``root``     : ``relative w-full`` wrapper anchoring the panel
- ``trigger``  : the bordered shell holding pills + input
- ``pills_row``: ``flex flex-wrap gap-1`` row of pills + input child
- ``input``    : the actual ``<input type="text">`` query field
- ``clear``    : the inline ``×`` to clear the whole picked value
- ``chevron``  : the trailing chevron icon
- ``panel``    : the absolute dropdown holding the filtered options.
                 Its ``max-h`` AND, when a custom ``trigger=`` detaches it
                 from the trigger's width, its ``min-w`` floor
                 (``sizes[<size>]["panel_free"]``) live in the size table
- ``header_bar`` : the sticky panel header (counter + pills + bulk actions)
- ``header_btn_primary`` / ``header_btn_muted`` : the bulk-action buttons
- ``option``   : each option button — base + size scaling
- ``option_active``   : highlighted-state modifier (hover / keyboard)
- ``option_check``    : the ✓ marking a PICKED option (multi only) —
                 the affordance ``option_selected``'s accent alone
                 cannot carry, since ``option_active`` is accented too
- ``option_selected`` : selected-state modifier (matches the value)
- ``empty``    : the "no results" placeholder shown when filter
                 returns 0 matches
"""

from __future__ import annotations

from typing import Any

COMBOBOX_THEME: dict[str, Any] = {
    "slots": {
        "root": "bz-combobox relative w-full",
        # The trigger shell holds pills + input. ``cursor-text`` so
        # the whole shell feels like a text input (clicking anywhere
        # focuses the inner ``<input>`` via the runtime).
        "trigger": (
            "flex items-center w-full rounded-field border-(length:--bz-stroke) "
            "border-text/10 bg-interface text-text "
            "cursor-text outline-none "
            "transition-all duration-200 "
            "focus-within:border-(--bz-solid) "
            "focus-within:ring-2 focus-within:ring-(--bz-focus-soft) "
            "focus-within:ring-offset-2 "
            "focus-within:ring-offset-background "
            "has-[input:disabled]:opacity-50 "
            "has-[input:disabled]:cursor-not-allowed "
            "has-[input:disabled]:bg-muted/10"
        ),
        # The flex row holding pills + input. ``min-w-0`` lets pills
        # truncate / wrap correctly when the value list grows.
        "pills_row": (
            "flex flex-wrap items-center gap-1 flex-1 min-w-0"
        ),
        # No pill classes here : pills source their styling from
        # :data:`bretzel.components.feedback.badge.theme.BADGE_THEME` via
        # ``_badge_pill_classes()`` (bottom of ``combobox.py``) — single
        # source of truth, a Badge tweak propagates here automatically.
        # The actual text input — borderless because the trigger
        # shell already carries the border. ``min-w-[60px]`` so the
        # input retains a typeable area when squeezed by pills.
        "input": (
            "flex-1 min-w-[60px] bg-transparent outline-none "
            "border-none p-0 text-text placeholder:text-muted/70 "
            "disabled:cursor-not-allowed"
        ),
        # ``×`` to clear everything. Hidden when there's nothing
        # picked. Hover gated on ``not-disabled:`` so the × stays frozen
        # when the parent Combobox is ``disabled`` — cf. traps.md §
        # "hover: sur un control disabled".
        "clear": (
            "shrink-0 inline-flex items-center justify-center "
            "ml-1 rounded-selector text-muted not-disabled:hover:text-text "
            "not-disabled:hover:bg-text/5 cursor-pointer outline-none "
            "focus-visible:ring-2 focus-visible:ring-(--bz-focus)"
        ),
        "chevron": (
            "shrink-0 ml-2 text-muted pointer-events-none "
            "transition-transform duration-200"
        ),
        # Positioned by ``$bz.helpers.floating`` (fixed + inline top/left,
        # min-width pinned to the trigger via ``match_width``). NO ``left-0
        # right-0`` : that leaves a ``right: 0`` which, under fixed
        # positioning, stretches the panel to the viewport's right edge
        # (cf. traps.md).
        # La hauteur max vit dans ``sizes[<size>]["panel"]`` (pas ici :
        # figée, un combobox ``xl`` couperait ses options).
        # ⚠️ ``mt-1`` et ``shadow-lg`` sont ALIGNÉS sur la famille des
        # panneaux ancrés, pas choisis ici : select, date_picker,
        # date_range_picker, dropdown et popover portent tous
        # ``shadow-lg``, et les trois qui ont un décalage portent ``mt-1``.
        # Combobox était le seul en ``mt-2 shadow-xl`` — deux champs
        # voisins dans un même formulaire ouvraient donc des panneaux
        # d'ombre et d'écart différents, alors que ``select/theme.py``
        # déclare que les deux doivent se lire comme UNE famille.
        # Gardé par ``tests/consistency/test_anchored_panels_match.py``.
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
        # **Header bar** — unified strip at the top of the panel.
        # Three zones, in flex-row :
        #   - LEFT : counter "N / total" (multi mode only)
        #   - MIDDLE : current picks rendered as removable pills
        #     (flex-wrap so long lists wrap gracefully without
        #     pushing the actions out of view)
        #   - RIGHT : Select all / Clear action buttons (only when
        #     ``bulk_actions=True`` AND multi mode)
        # Sticky top so it stays visible while scrolling long option
        # lists. Visible when there's something to show
        # (``_hasPicked()`` OR bulk-actions on) — completely hidden
        # otherwise (no chrome for nothing).
        "header_bar": (
            "flex flex-wrap items-center gap-2 px-2 py-1.5 "
            "border-b-(length:--bz-stroke) border-text/10 sticky top-0 "
            "bg-interface/95 backdrop-blur z-10"
        ),
        # Counter — "3 / 29" tabular-style. Subtle, secondary
        # information : muted text + small + tabular-nums so the
        # digits don't dance as the count changes.
        # La taille de texte vit dans ``sizes[<size>]["header_counter"]``
        # — ne PAS la remettre ici : le slot et la table s'écraseraient
        # mutuellement dans un ordre décidé par Tailwind (traps.md).
        "header_counter": (
            "shrink-0 text-muted tabular-nums"
        ),
        # Pills container — takes the remaining horizontal space
        # so the actions snap to the right edge. ``min-w-0`` lets
        # pills wrap correctly without overflowing.
        "header_pills": (
            "flex flex-wrap items-center gap-1 flex-1 min-w-0"
        ),
        # Actions container — right-aligned, small gap.
        "header_actions": (
            "shrink-0 inline-flex items-center gap-1 ms-auto"
        ),
        # Select all — primary action. Subtle by default (no
        # background), primary tint on hover so the constructive
        # nature reads at a glance.
        "header_btn_primary": (
            "inline-flex items-center px-2 py-1 rounded-selector "
            "font-medium text-(--bz-text) "
            "not-disabled:hover:bg-(--bz-bg) cursor-pointer "
            "outline-none focus-visible:ring-2 "
            "focus-visible:ring-(--bz-focus) "
            "disabled:opacity-50 disabled:cursor-not-allowed"
        ),
        # Clear — destructive action. Muted by default so it
        # doesn't compete visually with Select all ; error tint on
        # hover so the destructive intent is clear before clicking.
        "header_btn_muted": (
            "inline-flex items-center px-2 py-1 rounded-selector "
            "font-medium text-muted "
            "not-disabled:hover:bg-error/10 not-disabled:hover:text-error "
            "cursor-pointer outline-none focus-visible:ring-2 "
            "focus-visible:ring-error/40 "
            "disabled:opacity-50 disabled:cursor-not-allowed"
        ),
        "option": (
            "flex items-center w-full text-start "
            "px-3 py-2 cursor-pointer outline-none "
            "transition-colors duration-100 "
            "disabled:opacity-50 disabled:cursor-not-allowed"
        ),
        "option_active": "bg-(--bz-bg) text-(--bz-text)",
        # La coche d'une option prise (mode multi). ``ml-auto`` la pousse
        # au bord droit sans toucher l'alignement du libellé. La taille du
        # glyphe vit dans ``sizes[<size>]["check_icon_size"]`` — une icône
        # se taille en ``text-*``, jamais en ``w-``/``h-`` (traps.md).
        "option_check": "shrink-0 ms-auto text-(--bz-text)",
        "option_selected": "font-semibold text-(--bz-text)",
        # No-results placeholder.
        "empty": (
            "px-3 py-6 text-center text-muted/80"
        ),
    },
    # Échelle complète. Les clés en ``*_size`` ne sont PAS des classes :
    # ce sont les tokens de taille des sous-composants (Badge pour les
    # pills, Icon pour le chevron / la croix), lus par ``render()`` et
    # passés au constructeur. Convention reprise de ``BADGE_THEME``, qui
    # porte déjà ``icon_size`` / ``close_icon_size`` pour la même raison :
    # sans ça, un combobox ``xl`` embarque des pills ``sm``.
    #
    # ⚠️ Une icône se taille en ``text-*`` (via le token Icon), JAMAIS en
    # ``w-``/``h-`` — ``iconify-icon`` rend son glyphe à 1em (traps.md).
    #
    # ``md`` = l'apparence historique, inchangée au pixel près.
    "sizes": {
        "xs": {
            "trigger": "min-h-[1.75rem] px-2 py-0.5 text-xs",
            "input": "text-xs",
            "option": "text-xs",
            "check_icon_size": "xs",
            "panel": "max-h-48",
            "panel_free": "min-w-44",
            "empty": "text-xs",
            "header_counter": "text-[10px]",
            "header_btn_primary": "text-[10px]",
            "header_btn_muted": "text-[10px]",
            "pill_size": "xs",
            "chevron_size": "xs",
            "clear_icon_size": "xs",
        },
        "sm": {
            "trigger": "min-h-[2rem] px-3 py-1 text-xs",
            "input": "text-xs",
            "option": "text-xs",
            "check_icon_size": "xs",
            "panel": "max-h-52",
            "panel_free": "min-w-48",
            "empty": "text-xs",
            "header_counter": "text-xs",
            "header_btn_primary": "text-xs",
            "header_btn_muted": "text-xs",
            "pill_size": "xs",
            "chevron_size": "xs",
            "clear_icon_size": "xs",
        },
        "md": {
            "trigger": "min-h-[2.5rem] px-3 py-1.5 text-sm",
            "input": "text-sm",
            "option": "text-sm",
            "check_icon_size": "sm",
            "panel": "max-h-60",
            "panel_free": "min-w-56",
            "empty": "text-sm",
            "header_counter": "text-xs",
            "header_btn_primary": "text-xs",
            "header_btn_muted": "text-xs",
            "pill_size": "sm",
            "chevron_size": "sm",
            "clear_icon_size": "xs",
        },
        "lg": {
            "trigger": "min-h-[3rem] px-4 py-2 text-base",
            "input": "text-base",
            "option": "text-base",
            "check_icon_size": "md",
            "panel": "max-h-72",
            "panel_free": "min-w-64",
            "empty": "text-base",
            "header_counter": "text-sm",
            "header_btn_primary": "text-sm",
            "header_btn_muted": "text-sm",
            "pill_size": "md",
            "chevron_size": "md",
            "clear_icon_size": "sm",
        },
        "xl": {
            "trigger": "min-h-[3.5rem] px-5 py-2.5 text-lg",
            "input": "text-lg",
            "option": "text-lg",
            "check_icon_size": "lg",
            "panel": "max-h-80",
            "panel_free": "min-w-72",
            "empty": "text-lg",
            "header_counter": "text-base",
            "header_btn_primary": "text-base",
            "header_btn_muted": "text-base",
            "pill_size": "lg",
            "chevron_size": "lg",
            "clear_icon_size": "sm",
        },
    },
}
