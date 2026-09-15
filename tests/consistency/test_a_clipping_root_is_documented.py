"""Gate — un composant dont la racine CLIPPE est nommé dans la doc.

Le défaut qu'elle garde (finding [26], mesuré le 2026-08-21)
------------------------------------------------------------
La taille minimale automatique d'un flex-item ne vaut son contenu **que
si son débordement est visible**. Dès que la racine porte
``overflow-hidden`` (ou ``-auto`` / ``-scroll`` / ``-clip``),
``min-height: auto`` retombe à **zéro** : dans une colonne à hauteur
bornée, l'item se comprime et clippe son contenu — sans scrollbar
interne, sans erreur, sans rien.

Mesuré dans Chromium, 25 items dans une colonne ``h-[380px] min-h-0
overflow-y-auto`` : ``ui.table`` passe de 125 px à 11 (114 coupés),
``ui.card`` de 126 à 50, ``ui.accordion`` de 46 à 11, ``ui.toggle_group``
de 42 à 11. Les composants qui ne clippent pas leur racine (``ui.alert``,
``ui.banner``) tiennent à l'octet près — c'est toute la différence.

Et une sortie propre existe, mesurée elle aussi : ``ui.sidebar_item``
clippe (``overflow-x-hidden``) et **tient**, parce que sa racine porte
déjà ``shrink-0``. Un composant dont on sait qu'il ne sera jamais un
panneau réductible peut donc se protéger lui-même ; c'est pour ça que le
détecteur lit les DEUX classes, et pas seulement l'``overflow``.

Pourquoi une gate de DOC, et pas une correction
------------------------------------------------
La correction n'appartient pas au composant : poser ``shrink-0`` sur le
root de ``ui.card`` déplacerait le bug, parce qu'une carte est aussi un
PANNEAU (son usage dans une coque maître-détail) et qu'un panneau doit
pouvoir se réduire. La contrainte appartient au CONTENEUR, qui seul sait
s'il défile — et elle s'écrit ``[&>*]:shrink-0``, la quatrième classe de
l'idiome, celle que personne n'écrit.

Ce qui peut donc dériver n'est pas le code mais **la liste** : un
cinquième composant qui se met à clipper sa racine hérite du piège sans
que rien ne le dise. Cette gate lit la population dans le RENDU et exige
que ``traps.md`` la nomme. La doc devient vérifiable au lieu d'être
crue.

Ce qu'elle n'affirme pas
-------------------------
Que l'idiome documenté marche — ça, c'est
``tests/runtime_js/test_a_scrolling_column_does_not_crush_its_items.py``,
qui le mesure dans un navigateur et garde le témoin à trois classes.
"""

from __future__ import annotations

import functools
import re

import pytest

from tests.consistency._discovery import (
    REPO_ROOT,
    public_component_classes,
    rendered_html_of,
    ui_name_of,
)

#: ``overflow`` autre que ``visible`` sur la racine — la condition
#: EXACTE qui met ``min-height: auto`` à zéro. ``overflow-visible``
#: n'en fait pas partie, et c'est le seul mot qui ne doit pas matcher.
_CLIPS = re.compile(r"(?<![\w-])overflow(-[xy])?-(hidden|auto|scroll|clip)(?![\w-])")

#: La preuve que le détecteur mord vit sous un nom que la liste de
#: marqueurs ne devine pas : c'est un contrôle POSITIF — « le motif est
#: encore reconnu là où il DOIT l'être ». Un détecteur qui reconnaît un
#: cas réel n'est pas aveugle, et c'est la seule mutation qui ait un sens
#: ici (fabriquer une fausse classe ne dirait rien du corpus).
MUTATION_PROOF = "test_the_sweep_finds_the_known_clippers"

#: Le fichier qui doit les nommer.
_TRAPS = REPO_ROOT / ".claude" / "bretzel" / "traps.md"

#: Le plancher : au moins autant de composants publics que le balayage
#: en connaissait. Sans lui, une découverte cassée rendrait la gate
#: verte en ne trouvant AUCUNE racine clippante — donc rien à documenter.
_CATALOGUE_FLOOR = 90


@functools.cache
def clipping_roots() -> tuple[str, ...]:
    """Les composants publics dont la RACINE clippe son débordement.

    Lu dans le rendu, pas dans les thèmes : une classe peut arriver d'un
    variant, d'une taille ou d'un modificateur universel, et c'est ce qui
    sort qui décide du comportement CSS.
    """
    found: list[str] = []
    for cls in public_component_classes():
        html = rendered_html_of(cls)
        if not html:
            continue
        root = re.match(r"<[\w-]+[^>]*>", html)
        if root is None:
            continue
        klass = re.search(r'class="([^"]*)"', root.group(0))
        if klass is None:
            continue
        css = klass.group(1)
        # ``shrink-0`` sur la racine ANNULE le piège : l'item refuse de se
        # comprimer quoi qu'en dise sa taille minimale automatique.
        # Mesuré : ``ui.sidebar_item`` clippe (``overflow-x-hidden``) et
        # tient à l'octet près dans une colonne contrainte, parce qu'il
        # porte les deux. C'est la sortie propre pour un composant dont
        # on SAIT qu'il ne sera jamais un panneau réductible.
        if _CLIPS.search(css) and "shrink-0" not in css:
            found.append(ui_name_of(cls))
    return tuple(sorted(found))


def test_the_catalogue_is_not_vacuous() -> None:
    seen = public_component_classes()
    assert len(seen) >= _CATALOGUE_FLOOR, (
        f"seulement {len(seen)} composants publics découverts (97 mesurés "
        f"le 2026-08-19) : la gate jugerait sur un échantillon, et ne "
        f"trouverait aucune racine clippante à documenter."
    )


def test_the_sweep_finds_the_known_clippers() -> None:
    """Le contrôle POSITIF : le détecteur reconnaît les racines connues.

    Sans lui, une regex morte ferait passer la gate en ne trouvant plus
    personne — verte sur rien, la pathologie que ce répertoire a livrée
    trois fois.
    """
    found = clipping_roots()
    assert "card" in found and "accordion" in found, (
        f"le détecteur ne voit plus `ui.card` ni `ui.accordion` clipper "
        f"leur racine, alors que leurs thèmes posent `overflow-hidden`. "
        f"Il est aveugle. Trouvés : {found}"
    )


@pytest.mark.parametrize("name", clipping_roots(), ids=lambda n: n)
def test_a_clipping_root_is_named_in_traps(name: str) -> None:
    text = _TRAPS.read_text(encoding="utf8")
    assert f"`ui.{name}`" in text, (
        f"ui.{name} clippe sa racine, donc sa hauteur minimale "
        f"automatique vaut ZÉRO dans une colonne flex : il s'écrasera et "
        f"coupera son contenu dès que la liste sera assez longue pour "
        f"remplir la colonne — sans scrollbar, sans erreur.\n"
        f"  Il n'est nommé nulle part dans `.claude/bretzel/traps.md`. "
        f"Ajoute-le au § « Une colonne qui défile ÉCRASE ses items », qui "
        f"porte le mécanisme, la mesure et l'idiome à quatre classes."
    )


def test_the_trap_prescribes_the_fourth_class() -> None:
    """La doc doit porter le REMÈDE, pas seulement le diagnostic.

    C'est la seule chose qu'un lecteur vient chercher, et c'est celle qui
    ne se devine pas : `flex-1 min-h-0 overflow-y-auto` est de la culture
    générale Tailwind, `[&>*]:shrink-0` ne l'est pas.
    """
    text = _TRAPS.read_text(encoding="utf8")
    assert "[&>*]:shrink-0" in text, (
        "`traps.md` décrit l'écrasement sans donner la classe qui le "
        "répare — la moitié utile manque."
    )
