"""Default :class:`Video` theme.

Même parti que :mod:`bretzel.components.primitives.image.theme` : la
racine **est** l'élément média, sans enveloppe. Un ``<video>`` porte
lui-même ``aspect-ratio``, ``object-fit`` et un fond, donc la boîte
d'attente est son propre background.

Ce que ça donne sans une ligne de JS :

- **avant que les métadonnées arrivent**, la boîte au ratio déclaré
  occupe déjà sa place. Une vidéo est le pire cas du saut de page : le
  navigateur ne connaît ses dimensions qu'après un aller-retour réseau,
  donc sans ``ratio`` tout ce qui suit se décale une seconde plus tard ;
- **si la source casse**, la même boîte reste.

Le fond est ``bg-black`` et non le ``bg-muted/30`` de l'image — une
couleur de palette FIXE, donc une exception à la règle des tokens
sémantiques, déclarée dans ``test_themes_use_semantic_colours``.

La raison : ce noir n'est pas une surface de la page, c'est la **surface
d'un média**. Les bandes de letterboxing sont noires chez tous les
lecteurs, dans les deux modes, parce que la vidéo est étalonnée contre du
noir. Un ``bg-muted/30`` donnerait des bandes gris clair autour d'une
image sombre en mode clair, ce qui est le mauvais rendu — pas le rendu
« adapté au thème ».


⚠️ **La table de ratios est RECOPIÉE depuis le thème de l'image, à
dessein.** Les chaînes de classes visuelles restent par composant dans
ce dépôt — un token de style partagé couplerait deux thèmes qu'on doit
pouvoir faire diverger (le jour où une vidéo veut un ratio cinéma que
l'image n'a pas). La convention est harmonisée, pas factorisée.

Et comme chez l'image : table **fermée**, classes écrites en entier. Une
f-string ``aspect-[{w}/{h}]`` serait invisible au compilateur Tailwind de
prod — elle marcherait en dev et disparaîtrait au déploiement.
"""

from __future__ import annotations

from typing import Any

VIDEO_THEME: dict[str, Any] = {
    "slots": {
        # ``block`` : un élément média est ``inline`` par défaut, ce qui
        # lui colle l'espace de la ligne de base sous le ventre.
        # ``bg-black`` : LE fond qui sert de boîte d'attente (cf. docstring).
        "root": "block max-w-full bg-black",
    },
    "ratios": {
        "square": "aspect-square w-full",
        "video": "aspect-video w-full",
        "portrait": "aspect-[3/4] w-full",
        "wide": "aspect-[21/9] w-full",
    },
    # Comment l'image du média remplit le ratio déclaré. ``contain`` est
    # le défaut ici, à l'INVERSE de ``ui.image`` : recadrer une photo est
    # anodin, recadrer une vidéo coupe l'action — le letterboxing est le
    # comportement attendu de tout lecteur.
    "fits": {
        "contain": "object-contain",
        "cover": "object-cover",
    },
}
