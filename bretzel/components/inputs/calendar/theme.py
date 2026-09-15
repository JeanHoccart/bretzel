"""Default :class:`Calendar` theme.

Five visual zones :

- ``root`` : grid layout (header + weekday row + 6 week rows)
- ``header`` : month label + prev/next buttons row
- ``nav_button`` : the chevron buttons in the header
- ``month_label`` : centered ``"March 2026"`` text (les défauts sont
  ANGLAIS — cf. ``calendar.py`` ; le FR passe par ``month_names=``)
- ``weekday_row`` / ``weekday`` : the ``Sun Mon Tue Wed Thu Fri Sat``
  strip (défauts anglais, surchargeables via ``weekday_names=``)
- ``week_row`` : flex row of 7 day cells
- ``month_grid`` / ``month_cell`` : la grille d'ANNÉE du mode ``month``
  (12 cellules, 3 × 4) — un second type de grille, rendu à la place de
  ``weekday_row`` + ``week_row``, jamais en plus
- ``day_cell`` : each clickable day button
  - ``data-selected="true"`` : single-pick / range endpoints
  - ``data-in-range="true"`` : middles of an active range
  - ``data-today="true"`` : today (subtle ring)
  - ``data-outside="true"`` : day belonging to prev/next month (muted)
  - ``aria-disabled="true"`` : disabled day (min/max/disabled_dates)
"""

from __future__ import annotations

from typing import Any

CALENDAR_THEME: dict[str, Any] = {
    "slots": {
        "root": (
            # ⚠️ PAS de ``w-fit`` : la largeur vient de la table de
            # tailles (``sizes[<size>]["root"]``), et c'est un correctif,
            # pas une préférence. En ``w-fit`` la racine valait
            # ``max(en-tête, grille)`` — or le libellé du mois est du
            # texte de largeur variable, donc « septembre » élargissait
            # tout le calendrier. Mesuré le 2026-08-25 : 278 px en août,
            # 292,8 px en septembre, et **la flèche « mois suivant » se
            # déplaçait de 14,8 px**. On clique, la cible bouge, on doit
            # re-viser. (La hauteur, elle, ne bougeait pas : la grille
            # complète toujours ses 6 semaines.)
            "bz-calendar inline-flex flex-col gap-2 "
            "h-fit max-w-full "
            "p-3 rounded-box border-(length:--bz-stroke) border-text/10 bg-interface "
            "select-none "
            # Disabled feedback : whole grid fades + cursor reflects it.
            "aria-disabled:opacity-50 aria-disabled:cursor-not-allowed"
        ),
        # ``min-w-0`` : sans lui, un enfant flex refuse de rétrécir sous
        # sa taille de contenu, et le ``truncate`` du libellé ne se
        # déclencherait jamais — l'en-tête déborderait de la largeur
        # fixe au lieu de s'y plier.
        # ``gap-1.5`` et non ``gap-2`` : trois espaces à 6 px au lieu de
        # 8 rendent 6 px au libellé, assez pour que « septembre » ne
        # déclenche PAS le ``truncate`` à ``md``. Le truncate reste le
        # filet — une langue aux mois plus longs le trouvera.
        "header": "flex items-center justify-between gap-1.5 w-full min-w-0",
        "nav_button": (
            # Taille (``w-8 h-8`` md) dans ``sizes``, pas ici — cf. weekday.
            "inline-flex shrink-0 items-center justify-center rounded-selector "
            "text-text/70 not-disabled:hover:bg-text/5 not-disabled:hover:text-text "
            "disabled:opacity-40 disabled:cursor-not-allowed "
            "transition-colors"
        ),
        "month_label": "font-semibold text-text truncate min-w-0",
        "weekday_row": "grid grid-cols-7 gap-0",
        "weekday": (
            # ⚠️ Aucun token de TAILLE ici (w-/h-/text-<size>) : il vit
            # dans ``sizes[<size>]["weekday"]``, ``md`` compris. Les mettre
            # dans le slot les fait EMPILER avec la table → collision sur
            # le même élément (Tailwind tranche par l'ordre de sa feuille,
            # gagnant imprévisible). Cf. traps.md § « size= : collision
            # slot ↔ table ».
            "flex items-center justify-center "
            "font-medium text-text/50 uppercase tracking-wider"
        ),
        # La pastille d'une case marquée. ABSOLUE, et c'est le point :
        # posée dans le flux, elle transformerait la case en colonne et
        # décalerait le numéro du jour de TOUTES les cases, marquées ou
        # non. ``day_cell`` porte déjà ``relative``.
        #
        # ``pointer-events-none`` : la case entière est le bouton, la
        # pastille ne doit pas manger le clic. ``[&[data-selected=true]]``
        # la repasse en avant-plan sur un jour sélectionné, dont le fond
        # est déjà la couleur d'accent — sinon elle disparaîtrait dedans.
        "day_mark": (
            "pointer-events-none absolute left-1/2 -translate-x-1/2 "
            "rounded-full bg-(--bz-solid) "
            "[[data-selected=true]_&]:bg-(--bz-on-solid)"
        ),
        "week_row": "grid grid-cols-7 gap-0",
        # ── Mode ``month`` : une grille d'ANNÉE, 3 × 4 ───────────────
        # 3 colonnes et non 4 : les libellés sont des mots (« August »),
        # pas des nombres à deux chiffres, donc ils ont besoin de largeur.
        # Quatre colonnes forceraient l'abréviation, et abréger « Juin »
        # ne gagne rien.
        "month_grid": "grid grid-cols-3 gap-1 p-1",
        "month_cell": (
            "inline-flex items-center justify-center rounded-selector "
            "text-text not-disabled:hover:bg-text/5 "
            "transition-colors duration-150 cursor-pointer "
            "focus-visible:outline-none focus-visible:ring-2 "
            "focus-visible:ring-inset focus-visible:ring-(--bz-focus) "
            "data-[selected=true]:bg-(--bz-solid) "
            "data-[selected=true]:text-(--bz-on-solid) "
            "data-[selected=true]:font-semibold "
            "data-[current=true]:ring-1 data-[current=true]:ring-text/30 "
            "aria-disabled:opacity-40 aria-disabled:cursor-not-allowed "
            "aria-disabled:hover:bg-transparent"
        ),
        "day_cell": (
            # Idem — la taille (``w-9 h-9 text-sm`` pour md) vit dans
            # ``sizes``, pas ici.
            "relative inline-flex items-center justify-center "
            "rounded-selector "
            "text-text "
            "not-disabled:hover:bg-text/5 "
            "data-[outside=true]:text-text/30 "
            "data-[today=true]:ring-1 data-[today=true]:ring-text/30 "
            # Range middles : same ``--bz-bg`` wash, flat sides so they
            # tile seamlessly into the endpoints.
            "data-[in-range=true]:bg-(--bz-bg) "
            "data-[in-range=true]:rounded-none "
            # Range endpoints : flat the side that faces the in-range
            # so the bar reads as one continuous shape. Keep the
            # outer-facing side rounded.
            "data-[range-start=true]:rounded-r-none "
            "data-[range-end=true]:rounded-l-none "
            # Selected (single or range endpoints) wins last.
            "data-[selected=true]:bg-(--bz-solid) "
            "data-[selected=true]:text-(--bz-on-solid) "
            "data-[selected=true]:enabled:hover:bg-(--bz-solid) "
            # Per-cell disable (min/max/disabled_dates) rides
            # ``aria-disabled`` ; a WHOLE-calendar ``disabled`` stamps
            # the native ``disabled`` attr on every cell (JS ``_render``)
            # — mirror both so the cursor/opacity feedback matches the
            # convention (Button / Select : ``disabled:cursor-not-allowed``)
            # in both cases.
            "aria-disabled:opacity-30 aria-disabled:cursor-not-allowed "
            "aria-disabled:enabled:hover:bg-transparent "
            "disabled:opacity-30 disabled:cursor-not-allowed "
            "transition-colors"
        ),
        # ⚠️ Le slot ``event_dot`` a été RETIRÉ le 2026-08-01 : rien ne le
        # lisait (ni ``calendar.py``, ni ``07_calendar.js``, ni le
        # ``theme_blob``), et la docstring de ce fichier le rattachait à un
        # « mode view » qui n'existe pas (``_VALID_MODES = ("picker",
        # "range")``). Il reviendra avec un vrai ``ui.event_calendar``.
    },
    # 5 paliers — same scale as every other input (Input / Button /
    # Select / NumberInput / Slider / Combobox / Avatar). Each entry
    # overrides the slot baselines (which target ``md``).
    "sizes": {
        "xs": {
            # 224 px et non les 192 de la grille (7 × 24 + 24) : à ce
            # palier l'EN-TÊTE est plus large qu'elle. Mesuré en
            # français, « septembre » : 197 px de contenu contre 168 de
            # grille, et le trop-plein écrasait le chevron du sélecteur
            # de mois — « septembre2026 » collés. Les pistes de la
            # grille étant en ``1fr``, les cellules absorbent le
            # supplément ; ``w-6`` reste leur plancher.
            "root": "w-56",
            "day_mark": "w-1 h-1 bottom-0.5",
            "day_cell": "w-6 h-6 text-[10px]",
            "month_cell": "h-7 text-[10px]",
            "weekday": "w-6 h-5 text-[9px]",
            "nav_button": "w-6! h-6!",
            "month_label": "text-[11px]",
            "chevron": "text-[10px]",
        },
        "sm": {
            # 7 × 32 + 24 = 248 px : la grille, plus le ``p-3`` des deux bords.
            "root": "w-62",
            "day_mark": "w-1 h-1 bottom-1",
            "day_cell": "w-8 h-8 text-xs",
            "month_cell": "h-8 text-xs",
            "weekday": "w-8 h-6 text-[10px]",
            "nav_button": "w-7! h-7!",
            "month_label": "text-xs",
            "chevron": "text-xs",
        },
        "md": {
            # 7 × 36 + 24 = 276 px : la grille, plus le ``p-3`` des deux bords.
            "root": "w-69",
            # Le palier md vit dans la table comme les autres tailles
            # (dans les slots, il empilerait avec elles sur le même élément).
            "day_mark": "w-1.5 h-1.5 bottom-1",
            "day_cell": "w-9 h-9 text-sm",
            "month_cell": "h-9 text-sm",
            "weekday": "w-9 h-7 text-xs",
            "nav_button": "w-8! h-8!",
            "month_label": "text-sm",
            "chevron": "text-sm",
        },
        "lg": {
            # 7 × 44 + 24 = 332 px : la grille, plus le ``p-3`` des deux bords.
            "root": "w-83",
            "day_mark": "w-1.5 h-1.5 bottom-1.5",
            "day_cell": "w-11 h-11 text-base",
            "month_cell": "h-11 text-base",
            "weekday": "w-11 h-9 text-sm",
            "nav_button": "w-9! h-9!",
            "month_label": "text-base",
            "chevron": "text-base",
        },
        "xl": {
            # 7 × 13 + 6 = 97 crans : la grille, plus le ``p-3``
            # des deux bords.
            "root": "w-97",
            "day_mark": "w-2 h-2 bottom-1.5",
            "day_cell": "w-13 h-13 text-lg",
            "month_cell": "h-13 text-lg",
            "weekday": "w-13 h-10 text-base",
            # ⚠️ Douze crans (36 px) et non onze : le chevron de ce bouton
            # est un ``ui.icon`` au palier ``xl``, c'est-à-dire
            # ``text-4xl`` — 32 px de glyphe, qui ne tiennent pas dans
            # 33 px moins la bordure. Mesuré : 1,5 px dehors.
            "nav_button": "w-12! h-12!",
            "month_label": "text-lg",
            "chevron": "text-lg",
        },
    },
}
