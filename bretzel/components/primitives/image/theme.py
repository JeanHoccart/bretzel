"""Default :class:`Image` theme.

Un seul slot, parce que le composant est un seul élément : la racine
**est** l'``<img>``. Il n'y a pas de wrapper, et c'est le point de design
central — un ``<img>`` porte lui-même ``aspect-ratio``, ``object-fit`` et
un fond, donc la « boîte » du chargement est son propre background.

Ce que ça donne gratuitement, sans une ligne de JS :

- **avant le chargement** — la boîte au ratio déclaré occupe déjà sa
  place, en ``bg-muted/30``. C'est le skeleton, et c'est le même gris que
  ``ui.skeleton`` (voisin sémantique le plus proche : les deux disent
  « il y aura quelque chose ici ») ;
- **si l'URL casse** — la même boîte reste. Le navigateur pose son icône
  cassée et le texte ``alt`` par-dessus, mais la mise en page ne bouge
  pas.

C'est pour ça qu'il n'y a ni prop ``skeleton`` ni prop ``fallback`` :
les deux états sont le même objet, et cet objet est le fond de l'image.

⚠️ **Les ratios sont une table FERMÉE, écrits en entier.** Une f-string
qui composerait ``aspect-[{w}/{h}]`` produirait une classe que le
compilateur Tailwind ne voit jamais — elle marcherait en dev (compilateur
navigateur) et disparaîtrait en prod, avec un HTML identique des deux
côtés. Un ratio hors table se demande côté app en ``classes="aspect-[5/2]"``,
où Tailwind le scanne. Cf. la memory ``assembled_tailwind_class_dev_only``.
"""

from __future__ import annotations

from typing import Any

IMAGE_THEME: dict[str, Any] = {
    "slots": {
        # ``block`` : une image est ``inline`` par défaut, ce qui lui colle
        # l'espace de la ligne de base sous le ventre — un liseré fantôme
        # de quelques pixels dans toute carte qui l'entoure.
        # ``max-w-full`` : jamais de débordement horizontal du parent.
        # ``bg-muted/30`` : LE fond qui sert de skeleton ET de fallback.
        "root": "block max-w-full bg-muted/30",
    },
    # Table fermée — cf. l'avertissement du docstring.
    # ``w-full`` accompagne chaque ratio : ``aspect-ratio`` a besoin d'UNE
    # dimension pour dériver l'autre. Sans ratio, l'image garde sa taille
    # naturelle et ne reçoit aucune de ces classes.
    "ratios": {
        "square": "aspect-square w-full",
        "video": "aspect-video w-full",
        "portrait": "aspect-[3/4] w-full",
        "wide": "aspect-[21/9] w-full",
    },
    # Comment l'image remplit le ratio. Sans ``object-*``, une image dont
    # le ratio naturel diffère du ratio déclaré est ÉTIRÉE — c'est pour ça
    # que ``fit`` a une valeur par défaut plutôt que d'être optionnel.
    "fits": {
        "cover": "object-cover",
        "contain": "object-contain",
    },
}
