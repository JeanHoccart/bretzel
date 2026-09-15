"""``list="chips"`` change la STRUCTURE, pas seulement les classes.

Une présentation qui ne ferait que repeindre serait un mensonge : elle
existe précisément parce que le thème ne peut PAS l'obtenir. Mesuré le
2026-08-17 en essayant : override de cinq slots vers des puces, gain de
78 px sur 153, et le × continuait de flotter en badge de coin — parce
que ``absolute -top-2 -right-2`` n'est pas une question de classe mais
d'imbrication du DOM.

D'où cette gate. Elle exige trois différences **structurelles**, chacune
invérifiable par un simple diff de classes :

1. la puce n'émet **pas de vignette** — pas d'``<img>`` du tout ;
2. son × n'est **pas** en position absolue de coin ;
3. les deux arbres n'ont pas le même nombre de nœuds.

Pourquoi une présentation et pas une échappatoire
-------------------------------------------------

``FileUpload.COLLECTION_OWNER == "client"`` : la liste est peuplée par
le JS, en clonant un ``<template bz-for>`` au dépôt de fichier. Ni des
enfants Python ni un rappel ``render=`` ne l'atteignent — ils
s'exécuteraient au rendu serveur, quand la liste est vide. C'est la
troisième branche de la règle des collections (cf.
``test_collection_owner_decides_the_api``), et la seule dont la réponse
soit « livre les présentations toi-même ».

⚠️ Ce que cette gate ne dit PAS
--------------------------------

Elle lit le HTML SSR. Elle prouve que les deux arbres diffèrent, **pas**
qu'ils sont beaux ni que la puce tient sur une ligne. Le rendu réel de
la liste n'existe qu'après un dépôt de fichier, côté navigateur — donc
hors de portée de toute gate SSR. La vérification visuelle reste à la
charge d'un probe Playwright ou de l'œil.
"""

from __future__ import annotations

import re

import pytest

from bretzel import ui
from bretzel.components import FileUpload
from bretzel.components.base.attrs import ComponentDefinitionError
from bretzel.components.base.testing import render_isolated
from bretzel.components.inputs.file_upload.file_upload import LIST_PRESENTATIONS
from bretzel.core.serialize import serialize
from bretzel.theme import Theme

#: Preuve de morsure : une présentation inconnue doit LEVER à la construction ; les tests de
#: forme gardent le sens direct.
MUTATION_PROOF = "test_an_unknown_presentation_croaks_at_construction"


def _html(presentation: str) -> str:
    with render_isolated(theme=Theme()):
        return serialize(ui.file_upload(list=presentation).render())


def test_every_declared_presentation_renders() -> None:
    """Le plancher : chaque valeur de :data:`LIST_PRESENTATIONS` doit
    produire un rendu. Sans ça, on pourrait déclarer une présentation
    que personne ne bâtit, et les tests ci-dessous compareraient deux
    fois la même chose."""
    assert len(LIST_PRESENTATIONS) >= 2, (
        f"il ne reste que {len(LIST_PRESENTATIONS)} présentation(s) "
        f"({LIST_PRESENTATIONS}) — cette gate compare deux structures, "
        f"elle n'a plus rien à comparer."
    )
    for presentation in LIST_PRESENTATIONS:
        assert len(_html(presentation)) > 500, (
            f"list={presentation!r} ne rend rien de substantiel."
        )


def test_chips_emit_no_thumbnail() -> None:
    """Différence structurelle n°1 : le nœud ``<img>`` n'existe pas.

    Ce n'est pas une classe masquée — une puce n'a pas la place d'une
    vignette 80×64, donc le nœud n'est pas émis du tout. Une
    présentation qui poserait ``hidden`` dessus paierait quand même le
    ``URL.createObjectURL`` côté runtime."""
    tiles, chips = _html("tiles"), _html("chips")
    assert "<img" in tiles, (
        "la tuile a perdu sa vignette — ce test compare deux structures, "
        "il lui faut la référence."
    )
    assert "<img" not in chips, (
        "``list='chips'`` émet toujours une vignette. La puce doit ne pas "
        "émettre le nœud, pas le masquer : un nœud masqué coûte quand "
        "même son ``URL.createObjectURL`` au runtime."
    )


def test_the_chip_remove_button_is_inline() -> None:
    """Différence structurelle n°2, et la raison d'être de tout ceci.

    Le × de la tuile est un badge de coin (``absolute -top-2 -right-2``)
    qui déborde volontairement de la carte. Dans une puce il doit vivre
    DANS le flux, sinon il flotte au-dessus du texte voisin. C'est
    exactement ce que l'override de ``slots=`` n'a pas su faire."""
    tiles, chips = _html("tiles"), _html("chips")
    assert "-top-2" in tiles and "-right-2" in tiles, (
        "la tuile a perdu son × de coin — référence manquante."
    )
    assert "-top-2" not in chips and "-right-2" not in chips, (
        "le × de ``list='chips'`` est encore positionné en badge de coin. "
        "Une puce est une ligne : son × est dans le flux."
    )


def test_the_two_trees_differ_in_shape() -> None:
    """Différence structurelle n°3, la mesure grossière qui rattrape ce
    que les deux précédentes rateraient : un nombre d'éléments différent.

    Si un jour ``chips`` n'était plus qu'un jeu de classes, ce test
    rougirait même si quelqu'un avait pensé à contourner les deux
    assertions ci-dessus."""
    tiles, chips = _html("tiles"), _html("chips")
    n_tiles = len(re.findall(r"<[a-zA-Z]", tiles))
    n_chips = len(re.findall(r"<[a-zA-Z]", chips))
    assert n_tiles != n_chips, (
        f"les deux présentations émettent {n_tiles} éléments chacune. "
        f"``list=`` doit RESTRUCTURER — s'il ne change que des classes, "
        f"``slots=`` suffisait et cette prop ne mérite pas d'exister."
    )


def test_an_unknown_presentation_croaks_at_construction() -> None:
    """À la CONSTRUCTION, pas au rendu : un composant bâti puis écarté
    par une branche conditionnelle ne serait jamais rendu, et la faute
    ne remonterait jamais. Même contrat que ``variant=``."""
    with pytest.raises(ComponentDefinitionError) as exc, render_isolated():
        ui.file_upload(list="zznope")
    msg = str(exc.value)
    assert "zznope" in msg, "le message doit nommer la valeur fautive"
    assert "tiles" in msg and "chips" in msg, (
        "et lister les présentations disponibles, pour que l'auteur "
        "corrige sans aller lire le thème."
    )


def test_the_client_owner_is_declared() -> None:
    """La présentation n'a de sens que parce que le CLIENT possède la
    boucle. Si quelqu'un rendait un jour la liste côté serveur, la
    bonne réponse deviendrait un ``render=`` ou des enfants — et cette
    déclaration est ce qui rend ce raisonnement relisible."""
    assert FileUpload.COLLECTION_OWNER == "client", (
        "``FileUpload`` ne déclare plus que le client possède sa liste. "
        "Si c'est vrai, ``list=`` n'est plus la bonne réponse : relis "
        "``Component.COLLECTION_OWNER``."
    )
