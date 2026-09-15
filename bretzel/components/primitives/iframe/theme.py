"""Default :class:`Iframe` theme.

Même parti que ``image`` et ``video`` : la racine EST l'``<iframe>``, sans
enveloppe. Il porte lui-même ``aspect-ratio`` et un fond, donc la boîte
d'attente est son propre background.

Le ratio compte plus ici que partout ailleurs. Un embed est **la première
cause de saut de page** : le document distant met des centaines de
millisecondes à répondre, et sans hauteur réservée tout ce qui suit se
décale quand il arrive. Un ``<iframe>`` sans dimensions retombe d'ailleurs
sur un 300×150 hérité de 1996, que personne ne veut.

``bg-muted/30`` — le même que l'image, et non le noir de la vidéo : un
document embarqué est du contenu de page, pas un média étalonné contre du
noir. Une bordure discrète le détache de la page, parce qu'un document
tiers qui se fond dans la vôtre est trompeur autant qu'illisible.

Table de ratios **fermée** et **recopiée** (les chaînes de classes
restent par composant), classes écrites en entier — une f-string
``aspect-[{w}/{h}]`` serait invisible au compilateur Tailwind de prod.
"""

from __future__ import annotations

from typing import Any

IFRAME_THEME: dict[str, Any] = {
    "slots": {
        # ``block`` : un iframe est ``inline`` par défaut, ce qui lui colle
        # l'espace de la ligne de base sous le ventre.
        "root": (
            "block max-w-full bg-muted/30 "
            "border-(length:--bz-stroke) border-text/10 rounded-box"
        ),
    },
    "ratios": {
        "square": "aspect-square w-full",
        "video": "aspect-video w-full",
        "portrait": "aspect-[3/4] w-full",
        "wide": "aspect-[21/9] w-full",
    },
}
