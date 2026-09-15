"""Default :class:`FileUpload` theme.

Two variants — **dropzone** (large dashed area) and **button** (compact
inline trigger) — sharing the file-list strip below. Each ``size=``
palier (xs/sm/md/lg/xl) scales padding + icon + font + button height
in the ``sizes`` map below ; the render path picks the right one.

Key UX choices vs the V1 (juin 2026 refactor) :

- The remove ``×`` button floats **outside** the card edge
  (``-top-2 -right-2``) on a solid dark background, so it stays
  readable over any thumbnail. No more transparent-over-photo
  illegibility.
- The horizontal strip uses a custom thin scrollbar so the browser
  default scrollbar doesn't waste vertical real-estate (and we
  don't end up with a double scrollbar inside Card).
- The dropzone auto-shrinks when ``files.length > 0`` — the empty
  state collapses to a compact "Drop more files" hint. Mirror of
  Linear / Notion patterns.
- A global ``dragenter`` listener on ``window`` highlights every
  dropzone on the page when the user drags a file from the OS — the
  dropzone glows so the drop target is obvious from any
  scroll position.
"""

from __future__ import annotations

from typing import Any

FILE_UPLOAD_THEME: dict[str, Any] = {
    "slots": {
        # ``min-w-0`` : le root est souvent un flex/grid child dont le
        # ``min-width: auto`` par défaut le bloque à la min-content de son
        # contenu. Utile dans une **track contrainte** (grid ``1fr``, flex
        # stretch) pour qu'il respecte sa cellule. ⚠️ NE suffit PAS seul
        # contre un parent **shrink-to-fit** — c'est le ``w-0 min-w-full``
        # sur ``file_list`` (voir ce slot) qui empêche la strip de gonfler
        # l'ancêtre et fait vraiment marcher l'``overflow-x-auto``. Les deux
        # ensemble = robuste partout. Cf. traps.md § « overflow-x-auto défait
        # par min-width:auto » (famille du bug date_picker `w-fit`).
        "root": (
            "bz-file-upload flex flex-col gap-3 w-full min-w-0"
        ),
        # Native input — invisible, NOT focusable (tabindex=-1 on the
        # element itself ; ``sr-only`` alone leaves it in the tab
        # order). The wrapper is the focus host.
        "input_native": (
            "sr-only"
        ),
        # Validation panel.
        "error_panel": (
            "flex flex-col gap-1 w-full px-3 py-2 rounded-box "
            "bg-error/10 border-(length:--bz-stroke) border-error/20"
        ),
        "error_text": (
            "text-xs font-medium text-error"
        ),
        # File-list strip. ``items-start`` so a tall progress bar on
        # one item doesn't stretch the others. Custom scrollbar so
        # we don't double up with the page scrollbar — thin, themed,
        # only shows on hover.
        #
        # ``w-0 min-w-full`` (PAS ``w-full``) est load-bearing pour que
        # l'``overflow-x-auto`` se déclenche VRAIMENT. Avec ``w-full``, la
        # min-content de la strip = la SOMME des cartes ``shrink-0`` ; un
        # parent shrink-to-fit (``vstack align=start``, cellule grid,
        # ``inline-flex``…) se dimensionne alors sur cette somme → la strip
        # gonfle son ancêtre au lieu de scroller, et le trop-plein est clippé
        # (aucune scrollbar). ``width:0 ; min-width:100%`` casse la boucle :
        # la contribution max-content de la strip devient 0 (elle ne tire plus
        # l'ancêtre), mais elle remplit 100% du parent → les cartes débordent
        # SA largeur → ``overflow-x-auto`` scrolle enfin. Robuste dans tout
        # contexte (mesuré : shrink-parent ET full-width). Cf. traps.md
        # § « overflow-x-auto défait par min-width:auto ». Le ``min-w-0`` sur
        # le root reste utile (cellule grid plus étroite que la dropzone).
        #
        # Padding trade-off : the remove × button floats ``-top-2
        # -right-2`` (8px outside the card corner). Combined with
        # ``overflow-y: hidden`` (needed to prevent a stray vertical
        # scrollbar) this clips the button. Counter-padding ``pt-3
        # pr-3`` keeps the same overflow constraint AND gives the
        # floating buttons room to render without clipping.
        "file_list": (
            "flex flex-row items-start w-0 min-w-full gap-3 pt-3 pr-3 pb-2 "
            "snap-x overflow-x-auto overflow-y-hidden empty:hidden "
            # ⚠️ Ces six variantes NE S'APPLIQUENT PAS EN DEV — mesuré le
            # 2026-08-29 : l'élément les porte toutes, et les feuilles de
            # la page ne contiennent aucune règle préfixée pour elles, donc
            # la bande hérite de la barre 4 px globale au lieu de sa 1.5.
            # En PROD elles compilent (vérifié au binaire, six règles
            # ``::-webkit-scrollbar`` émises) : ce n'est donc pas une
            # erreur d'écriture mais une divergence dev/prod, la même
            # famille que ``theme/css.py`` § ``_NO_SCROLLBAR``.
            #
            # Gardées telles quelles : la forme est juste, et les
            # remplacer par un hook maison irait contre la préférence
            # établie (du Tailwind standard écrit par le dev plutôt qu'un
            # utilitaire propriétaire). Ce qui se répare, c'est le mode
            # dev — cf. la décision ouverte dans ``work/todo.md``.
            "[&::-webkit-scrollbar]:h-1.5 "
            "[&::-webkit-scrollbar-track]:bg-transparent "
            "[&::-webkit-scrollbar-thumb]:bg-text/10 "
            "[&::-webkit-scrollbar-thumb]:rounded-full "
            "[&::-webkit-scrollbar-thumb]:transition-colors "
            "hover:[&::-webkit-scrollbar-thumb]:bg-text/25"
        ),
        # File card. ``overflow-visible`` so the floating × button
        # can stick out of the corner. ``shrink-0`` prevents the
        # horizontal flex container from squishing items.
        "file_item": (
            "group relative shrink-0 flex flex-col items-center "
            "justify-start w-28 p-2 rounded-box border-(length:--bz-stroke) border-text/10 "
            "bg-interface shadow-sm hover:border-(--bz-border-hover) "
            "hover:bg-(--bz-bg) transition-all snap-start"
        ),
        # ── Présentation « chips » (``list="chips"``) ──────────────
        #
        # PAS un restyle des tuiles : une autre STRUCTURE. La tuile est
        # une colonne (`flex-col w-28`) avec une vignette et un × en
        # badge de coin (`absolute -top-2 -right-2`) ; la puce est une
        # ligne (`flex-row`) sans vignette, dont le × est INLINE. Aucune
        # classe ne fait passer de l'un à l'autre — c'est l'imbrication
        # du DOM qui change, et c'est précisément ce que `slots=` ne
        # peut pas faire (mesuré : +78 px après override de 5 slots, et
        # le × flottait toujours).
        #
        # Préfixe ``chip_`` : la convention de CE fichier pour une
        # présentation alternative (cf. ``dropzone_*`` / ``button_*``
        # pour l'axe ``variant=``).
        "chip_list": (
            "flex flex-row flex-wrap items-center gap-2 pt-3 empty:hidden"
        ),
        "chip_item": (
            "group relative inline-flex flex-row items-center gap-1.5 "
            "max-w-full pl-2 pr-1 py-1 rounded-full border-(length:--bz-stroke) border-text/10 "
            "bg-interface hover:border-(--bz-border-hover) "
            "hover:bg-(--bz-bg) transition-all"
        ),
        "chip_icon": (
            "inline-flex shrink-0 items-center justify-center "
            "text-(--bz-text) text-sm"
        ),
        "chip_name": (
            "truncate text-xs font-medium text-text"
        ),
        # Statuts INLINE — la tuile les pose en ``absolute top-1 left-1``
        # sur sa vignette, une puce n'en a pas.
        "chip_status_done": (
            "inline-flex shrink-0 items-center justify-center w-4 h-4 "
            "rounded-full bg-success text-white"
        ),
        "chip_status_error": (
            "inline-flex shrink-0 items-center justify-center w-4 h-4 "
            "rounded-full bg-error text-white"
        ),
        "chip_progress_bar": (
            "absolute bottom-0 left-0 right-0 h-0.5 bg-text/5 "
            "rounded-b-full overflow-hidden"
        ),
        # × INLINE, dans le flux de la puce — la différence structurelle
        # qui a motivé toute cette présentation.
        "chip_remove_btn": (
            "relative shrink-0 inline-flex items-center justify-center "
            "rounded-full text-muted hover:bg-error hover:text-white "
            "active:scale-90 active:bg-error active:text-white "
            "transition-colors"
        ),
        "file_thumb": (
            "w-20 h-16 mb-2 rounded-selector object-cover bg-background"
        ),
        "file_icon": (
            "w-10 h-10 mb-2 inline-flex items-center justify-center "
            "text-(--bz-text) text-3xl "
            "transition-transform group-hover:scale-110"
        ),
        "file_name": (
            "w-full truncate text-center text-xs font-semibold text-text"
        ),
        "file_size": (
            "w-full text-center text-[10px] text-muted"
        ),
        # Async upload progress (per-file bar at the bottom of the card).
        "file_progress_bar": (
            "absolute bottom-0 left-0 right-0 h-1 bg-text/5 "
            "rounded-b-box overflow-hidden"
        ),
        "file_progress_fill": (
            "h-full bg-(--bz-solid) transition-all duration-150"
        ),
        # Status badges over the thumb / icon.
        "file_status_done": (
            "absolute top-1 left-1 inline-flex items-center "
            "justify-center w-5 h-5 rounded-full bg-success text-white "
            "shadow-sm"
        ),
        "file_status_error": (
            "absolute top-1 left-1 inline-flex items-center "
            "justify-center w-5 h-5 rounded-full bg-error text-white "
            "shadow-sm"
        ),
        "file_status_icon": (
            "inline-flex shrink-0 text-current text-[10px]"
        ),
        # Per-file remove button — solid, floats OUTSIDE the card
        # corner so it never overlaps the thumb.
        # TOUJOURS visible — pas de révélation au survol. Tailwind v4
        # enveloppe chaque variante ``hover:`` dans ``@media (hover: hover)``
        # (rupture v3→v4) : sur un appareil tactile la règle n'existe pas,
        # donc un x posé à ``opacity-0`` restait invisible POUR TOUJOURS et
        # le seul moyen de retirer un fichier devenait inatteignable
        # (reproduit au navigateur, cf. traps.md). Le montrer en permanence
        # règle le fond plutôt que de compenser le symptôme : une action
        # ne se cache pas derrière un geste que l'appareil ne sait pas
        # produire. ``active:`` (et non ``hover:``) porte le retour au
        # toucher, qui lui marche partout.
        # Pas de dimension ici : la boîte vient de ``sizes["remove_btn"]``
        # et le glyphe de ``sizes["remove_btn_icon_size"]``, sinon le x
        # reste figé quel que soit le ``size=`` du composant (famille
        # « enfant figé », cf. _FROZEN_CHILD_BASELINE). Badge est le modèle.
        "remove_btn": (
            "absolute -top-2 -right-2 inline-flex items-center "
            "justify-center rounded-full bg-text text-background "
            "shadow-md hover:bg-error hover:text-white "
            "active:scale-90 active:bg-error active:text-white "
            "focus-visible:outline-none "
            "focus-visible:ring-2 focus-visible:ring-error/50 "
            "transition-all"
        ),
        # variant=dropzone — the big dashed area. Padding + content
        # scale via the ``sizes`` map below ; this slot only owns
        # the colour / focus / interactive parts.
        #
        # Neutral at REST, like an Input : a dashed ``border-text/15``
        # over ``bg-interface``, no colour tint until the user engages.
        # The coloured accent lives ONLY in the interactive states
        # — hover (border + faint fill), focus ring, and the drag
        # highlights (``dropzone_active`` / ``dropzone_global_drag``).
        # Trade-off : ``color="success"`` vs ``color="primary"`` now
        # read identically at rest and only diverge on hover / focus /
        # drag — deliberate, to keep the resting component calm.
        "dropzone_wrapper": (
            "group relative flex flex-col items-center justify-center "
            "w-full rounded-box border-(length:--bz-stroke-strong) border-dashed "
            "border-text/15 bg-interface cursor-pointer "
            "transition-all duration-200 "
            "hover:border-(--bz-border-hover) hover:bg-(--bz-bg) "
            "has-[:disabled]:opacity-50 has-[:disabled]:cursor-not-allowed "
            "outline-none focus-visible:border-(--bz-solid) "
            "focus-visible:ring-2 focus-visible:ring-offset-2 "
            "focus-visible:ring-offset-background "
            "focus-visible:ring-(--bz-focus)"
        ),
        # Class added by ``bz-attr:class`` when the user is dragging
        # files OVER this dropzone (vs the global highlight, which
        # signals a drag on the page — see ``dropzone_global_drag``).
        "dropzone_active": (
            "border-(--bz-solid) bg-(--bz-bg) scale-[0.99]"
        ),
        # Highlight added when ``isGlobalDragActive`` is true — a
        # file is being dragged anywhere on the page, every dropzone
        # surfaces itself.
        "dropzone_global_drag": (
            "border-(--bz-solid)/60 bg-(--bz-bg) "
            "ring-2 ring-(--bz-focus-soft) ring-offset-2 "
            "ring-offset-background"
        ),
        "dropzone_empty_state": (
            "flex flex-col items-center justify-center pointer-events-none"
        ),
        # Neutral ``text-muted`` at rest ; lights up in the colour on
        # hover — mirror of the Input icon slots' ``group-focus-within``
        # behaviour.
        "dropzone_icon": (
            "inline-flex shrink-0 text-muted "
            "group-hover:text-(--bz-text) transition-all duration-200 "
            "group-hover:-translate-y-0.5"
        ),
        "dropzone_title": (
            "font-semibold text-text text-center"
        ),
        "dropzone_subtitle": (
            "text-muted text-center"
        ),
        # variant=button — compact inline trigger. Neutral at rest like
        # an Input (``border-text/10`` + ``bg-interface`` + ``text-text``)
        # so it sits calm next to a primary CTA ; the coloured
        # accent surfaces on hover (border + text + faint fill) and the
        # focus ring. The icon rides ``text-current``, so it follows the
        # label colour through the hover transition automatically.
        "button_wrapper": (
            "inline-flex items-center justify-center gap-2 "
            "rounded-field border-(length:--bz-stroke) border-text/10 bg-interface "
            "text-text font-medium cursor-pointer transition-all "
            "hover:bg-(--bz-bg) hover:border-(--bz-border-hover) "
            "hover:text-(--bz-text) "
            "has-[:disabled]:opacity-50 has-[:disabled]:cursor-not-allowed "
            "outline-none focus-visible:ring-2 focus-visible:ring-offset-2 "
            "focus-visible:ring-offset-background "
            "focus-visible:ring-(--bz-focus)"
        ),
        "button_icon": (
            "inline-flex shrink-0 text-current"
        ),
    },
    # ── Size paliers ─────────────────────────────────────────────────
    # Each size scales the visual weight of dropzone padding /
    # icon-size / title-text-size / button height. Read manually in
    # ``FileUpload.render`` because we want size-specific decisions on
    # multiple sub-elements (not just the root).
    "sizes": {
        # ⚠️ **Le padding est coupé par AXE, et c'est un fix, pas un style.**
        #
        # Jusqu'au 2026-08-29 l'axe vertical vivait dans les DEUX couches :
        # ``px-6 py-8`` en ``class=`` statique, ``py-3`` ajouté en
        # ``bz-class`` quand des fichiers sont là. Or les deux utilitaires
        # ont la MÊME spécificité — c'est l'ordre de la feuille Tailwind qui
        # tranche, pas l'ordre d'ajout au ``classList``. Mesuré : un élément
        # portant ``py-8 py-3`` calcule ``padding-top: 32px``, donc l'état
        # compact **ne s'appliquait jamais**.
        #
        # D'où trois tables au lieu de deux : l'horizontal est identique
        # dans les deux états et reste statique ; le vertical est
        # EXCLUSIVEMENT porté par la couche dynamique, qui émet le ternaire
        # complet. C'est le motif d'``accordion.py`` (« les deux classes de
        # rangée vivent exclusivement dans le ``bz-class`` »).
        #
        # ⚠️ Ne PAS remettre un ``py-*`` ici : la redite est invisible au
        # HTML, elle ne se voit qu'au ``getComputedStyle``.
        "dropzone_padding_x": {
            "xs": "px-3",
            "sm": "px-4",
            "md": "px-6",
            "lg": "px-8",
            "xl": "px-10",
        },
        # L'état VIDE — la grande zone d'accueil.
        "dropzone_padding_y": {
            "xs": "py-3",
            "sm": "py-5",
            "md": "py-8",
            "lg": "py-12",
            "xl": "py-16",
        },
        # L'état AVEC FICHIERS : la dropzone se ramasse en un rappel
        # « déposer encore ». Même axe que ci-dessus, donc les deux ne
        # peuvent coexister — le ternaire en choisit une.
        "dropzone_padding_with_files": {
            "xs": "py-2",
            "sm": "py-2.5",
            "md": "py-3",
            "lg": "py-4",
            "xl": "py-5",
        },
        "dropzone_icon_size": {
            "xs": "text-lg",
            "sm": "text-xl",
            "md": "text-3xl",
            "lg": "text-4xl",
            "xl": "text-5xl",
        },
        # Icon shrinks when the dropzone is compact (files present).
        "dropzone_icon_size_with_files": {
            "xs": "text-sm",
            "sm": "text-base",
            "md": "text-xl",
            "lg": "text-2xl",
            "xl": "text-3xl",
        },
        "dropzone_icon_margin": {
            "xs": "mb-1",
            "sm": "mb-2",
            "md": "mb-3",
            "lg": "mb-3",
            "xl": "mb-4",
        },
        "dropzone_icon_margin_with_files": {
            "xs": "mb-0.5",
            "sm": "mb-1",
            "md": "mb-1.5",
            "lg": "mb-2",
            "xl": "mb-2",
        },
        "dropzone_title": {
            "xs": "text-xs",
            "sm": "text-sm",
            "md": "text-sm",
            "lg": "text-base",
            "xl": "text-lg",
        },
        "dropzone_subtitle": {
            "xs": "text-[10px] mt-0.5",
            "sm": "text-[10px] mt-1",
            "md": "text-xs mt-1",
            "lg": "text-sm mt-1",
            "xl": "text-base mt-1.5",
        },
        "button_padding": {
            "xs": "px-2 h-7 text-xs",
            "sm": "px-3 h-8 text-sm",
            "md": "px-4 h-10 text-sm",
            "lg": "px-5 h-12 text-base",
            "xl": "px-6 h-14 text-lg",
        },
        "button_icon_size": {
            "xs": "text-xs",
            "sm": "text-sm",
            "md": "text-base",
            "lg": "text-lg",
            "xl": "text-xl",
        },
        # Le x de retrait suit le ``size=`` du composant — boîte ici,
        # glyphe juste en dessous. Sans ça il restait à ``w-6 h-6`` /
        # ``text-xs`` à TOUS les paliers (mesuré) : la carte grandissait,
        # son x non.
        "remove_btn": {
            "xs": "w-5 h-5",
            "sm": "w-5 h-5",
            "md": "w-6 h-6",
            "lg": "w-7 h-7",
            "xl": "w-8 h-8",
        },
        # Valeurs = noms de tailles d'``Icon`` (pas des classes ``text-*``),
        # c'est ``Icon`` qui possède l'échelle du glyphe. Même contrat que
        # ``close_icon_size`` chez Badge.
        "remove_btn_icon_size": {
            "xs": "xs",
            "sm": "xs",
            "md": "xs",
            "lg": "sm",
            "xl": "sm",
        },
    },
}
