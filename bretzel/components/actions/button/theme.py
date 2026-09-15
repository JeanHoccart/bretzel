"""Default :class:`Button` theme.

- ``transition-all duration-200 ease-out`` + ``not-disabled:active:scale`` for
  tactile click feedback.
- Solid : brightness + shadow hover lift ; outline / ghost / soft :
  opacity-driven hover (``/10`` → ``/20``).
- Focus ring : ``ring-2 ring-offset-2 ring-{color}/40``.
"""

from __future__ import annotations

from typing import Any

BUTTON_THEME: dict[str, Any] = {
    "slots": {
        "root": (
            # Layout
            "inline-flex items-center justify-center "
            # Shape
            "rounded-field font-medium "
            # Motion + tactile feedback
            "transition-all duration-200 ease-out "
            "not-disabled:active:scale-[0.95] "
            # Focus ring
            "focus-visible:outline-none focus-visible:ring-2 "
            "focus-visible:ring-offset-2 focus-visible:ring-offset-background "
            "focus-visible:ring-(--bz-focus) "
            # ``loading=True`` also flips the HTML ``disabled`` attr (render())
            # so this one variant covers both states.
            "disabled:opacity-50 disabled:cursor-not-allowed "
            # ── Le même état, quand la balise est un ``<a>`` ──────────
            # ``ui.button(href=…)`` rend un ancre, et ``:disabled`` ne
            # matche JAMAIS un ``<a>`` : sans ces jumeaux, un lien-bouton
            # désactivé s'affichait à pleine opacité, curseur normal, et
            # s'éclaircissait encore au survol. Le ``render`` pose
            # ``aria-disabled`` + ``tabindex=-1`` et retire la
            # destination — donc il ne navigue pas ; ce qui manquait
            # était de le MONTRER.
            #
            # ⚠️ Le ``!`` est load-bearing, et pour une raison mesurable
            # qui ne vaut PAS chez ``ui.link``. Là-bas les variantes
            # survolent en ``hover:*`` nu (0,2,0), donc un
            # ``aria-disabled:hover:*`` (0,3,0) les bat par simple
            # spécificité et le thème s'en explique. Ici les variantes
            # écrivent ``not-disabled:hover:*``, qui pèse **aussi**
            # 0,3,0 : à égalité, c'est l'ordre dans la feuille qui
            # tranche, et cet ordre appartient au compilateur.
            "aria-disabled:opacity-50 aria-disabled:cursor-not-allowed "
            "aria-disabled:hover:brightness-100! "
            "aria-disabled:hover:shadow-none! "
            "aria-disabled:active:scale-100!"
        ),
        "icon": "shrink-0",
    },
    "variants": {
        # Solid : full background + foreground colour, hover lifts via
        # brightness + a subtle shadow rather than a flat alpha bump.
        "solid": (
            "bg-(--bz-solid) text-(--bz-on-solid) shadow-sm "
            "not-disabled:hover:brightness-110 not-disabled:hover:shadow-md"
        ),
        # Outline : 2px border so the click target reads as a button
        # even before hover. Hover fills with /10 alpha of the colour.
        "outline": ("border-(length:--bz-stroke-strong) border-(--bz-solid) text-(--bz-text) not-disabled:hover:bg-(--bz-bg)"),
        # Ghost : NO box at rest — coloured text, and a /10 wash on
        # hover. That is a deliberate emphasis level, not a lighter
        # ``soft``, and it constrains WHERE it belongs :
        #
        #   ghost va DANS un conteneur qui dessine déjà la boîte.
        #
        # Une rangée de menu, une cellule d'en-tête teintée, un pied de
        # dialogue à côté d'un ``solid`` : le contenant porte la limite,
        # le bouton n'apporte que la zone de clic et les affordances.
        # Un contrôle AUTONOME — une barre d'outils, un bouton seul en
        # fin de liste — n'a pas ce contenant : au repos il ne se
        # distingue plus du texte, et ``hover:`` ne peut pas rattraper
        # ça. C'est la règle que ``theme/tailwind.py`` pose au bout de sa
        # note sur ``@custom-variant hover`` : « ``hover:`` must still
        # never CARRY an affordance ». Elle ne parle pas que du tactile —
        # avant le survol, personne ne voit rien, souris ou pas.
        #
        # Pour un contrôle autonome discret : ``soft`` (boîte lavée) ou
        # ``outline`` (boîte bordée). Donner une boîte au repos à
        # ``ghost`` le ferait fondre dans ``soft`` et lui retirerait sa
        # raison d'être — c'est la doctrine qui manquait, pas le CSS.
        #
        # ⚠️ Non gaté, et c'est mesuré : interdire « une boîte seulement
        # sous hover » dans les thèmes donne 24 occurrences dont 22
        # légitimes (sidebar, dropdown, calendrier, pagination — un
        # ``hover:`` qui enrichit une rangée dans une liste bornée est le
        # motif dominant ET correct). La dérive ici est « quelle variante
        # à ce call-site, vu ce qui l'entoure », et ça ne se décide pas
        # statiquement : on ne voit pas dans la source si le parent
        # dessine une boîte. D'où de la doctrine, et pas un test.
        "ghost": ("text-(--bz-text) not-disabled:hover:bg-(--bz-bg)"),
        # Surface : le contrôle se lit comme un CHAMP — même boîte bordée
        # que ``ui.input``. C'est ce qui manquait pour qu'une barre
        # d'outils mêlant une recherche et des boutons se lise comme UNE
        # famille : `soft` donne un lavis sans bordure, `outline` une
        # bordure de 2 px accentuée, et aucun des deux ne ressemble au
        # champ voisin (`bg-interface` + `border-text/10`).
        #
        # La couleur reste un point d'accroche (`text-(--bz-text)`) pour
        # que la règle « l'accent marque le pair ACTIF » continue de
        # s'appliquer sans changer la boîte : au repos `current`, actif
        # l'accent — la géométrie ne bouge pas.
        "surface": (
            "bg-interface border-(length:--bz-stroke) border-text/10 text-(--bz-text) "
            "not-disabled:hover:bg-text/5"
        ),
        # Soft : muted background, hover bumps to /20.
        "soft": ("bg-(--bz-bg) text-(--bz-text) not-disabled:hover:bg-(--bz-bg-hover)"),
    },
    "sizes": {
        "xs": "h-7 px-2 text-xs gap-1",
        "sm": "h-8 px-3 text-sm gap-1.5",
        "md": "h-10 px-4 text-sm gap-2",
        "lg": "h-12 px-6 text-base gap-2",
        "xl": "h-14 px-8 text-base gap-2.5",
    },
    # No ``modifiers`` map — the disabled visual lives at the root slot via
    # the ``disabled:`` Tailwind variant, reactive through the HTML attribute.
}
