"""L'écart d'un anneau de focus doit valoir le fond sur lequel il repose.

``ring-offset-N`` ne creuse pas un trou : il **peint** N pixels de la
couleur ``--tw-ring-offset-color``. Cet écart n'est invisible que si sa
couleur est exactement celle du fond derrière l'élément focalisé.

Le cas qui a motivé la gate (2026-08-15)
-----------------------------------------
``SidebarItem`` portait ``focus-visible:ring-offset-background``, alors
que l'``<aside>`` qui le contient est ``bg-surface``. Mesuré au
navigateur : ``--tw-ring-offset-shadow: 0 0 0 2px rgb(2 6 23)`` sur un
aside en ``rgb(15 23 42)`` — soit un liseré NOIR autour de chaque entrée
focalisée, au lieu de rien. ``NavbarItem`` portait la même faute, pour la
même raison (son ``<header>`` est aussi ``bg-surface``).

Pourquoi c'est une classe et pas deux accidents
------------------------------------------------
``ring-offset-background`` apparaît **31 fois** dans le catalogue et il
est juste 29 fois : un bouton, un input, une case à cocher sont posés sur
le fond de PAGE. La convention est donc bonne par défaut, et c'est
précisément ce qui la rend piégeuse — on la recopie sans voir que le
composant qu'on écrit peint sa PROPRE surface sous ses enfants
focusables. Il n'y a que les conteneurs pour ça, et ils sont rares.

La règle retenue
-----------------
**Si le slot ``root`` d'un thème peint ``bg-<token>``, alors tout
``ring-offset-<couleur>`` du même fichier doit être ce même token.**

Elle se vérifie sans rendu et n'a aucun faux positif sur le catalogue
actuel, parce qu'elle ne regarde que le fond du ROOT :

- les inputs peignent ``bg-interface`` sur **eux-mêmes**, pas sur un
  conteneur — mais c'est bien leur root, donc ils sont dans le périmètre
  et devraient déclarer ``ring-offset-interface``… sauf qu'ils sont
  posés sur la page. D'où la restriction aux tokens de SURFACE
  ci-dessous : ``interface`` est une teinte de contrôle, ``surface`` une
  teinte de panneau. Seul le second implique « je suis le fond de mes
  enfants ».
- ``carousel`` porte ``bg-surface`` mais **pas sur son root** (c'est le
  fond de survol de ses flèches) : hors périmètre, automatiquement.

Alternative écartée, et pourquoi
---------------------------------
``bottom_bar`` résout le même problème avec ``focus-visible:ring-inset``
— l'anneau est dessiné À L'INTÉRIEUR, donc ni écart à colorer ni
débordement à rogner. C'est plus simple, et la tentation d'aligner la
sidebar dessus est réelle. **Elle ne marche pas ici** : la ligne active
d'une sidebar est un aplat ``bg-{bg_color}``, et un anneau
``ring-{bg_color}/40`` dessiné à l'intérieur de cet aplat est la même
couleur sur elle-même — invisible. La bottom bar peut se le permettre
parce que son état actif ne fait que RECOLORER le texte, sans aplat.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from tests.consistency._discovery import (
    ParsedSource,
    theme_slot_strings,
    theme_sources,
)

_COMPONENTS = Path(__file__).resolve().parents[2] / "bretzel" / "components"
_THEMES = theme_sources()

#: Les tokens qui désignent un PANNEAU — un fond que le composant pose
#: sous ses enfants. ``interface`` en est exclu à dessein : c'est le
#: remplissage d'un CONTRÔLE (input, bouton), qui ne devient pas pour
#: autant le fond de ce qu'il contient.
_SURFACE_TOKENS = frozenset({"surface"})

_BG = re.compile(r"(?<![-\w])bg-([a-z]+)(?![\w-])")
_RING_OFFSET_COLOR = re.compile(r"(?<![-\w])ring-offset-([a-z][a-z-]*)")


def _root_surface(source: str) -> str | None:
    """Le token de panneau peint par le slot ``root``, s'il y en a un.

    On lit le PREMIER slot nommé ``root`` du fichier — celui du composant
    conteneur. Les thèmes de ses enfants (``SIDEBAR_ITEM_THEME``…) vivent
    plus bas dans le même fichier, ce qui est exactement la relation
    qu'on veut vérifier : le conteneur peint, l'enfant pose son anneau.
    """
    for slot, classes in theme_slot_strings(source):
        if slot != "root":
            continue
        painted = set(_BG.findall(classes)) & _SURFACE_TOKENS
        if painted:
            return next(iter(painted))
    return None


def _offset_colors(source: str) -> set[str]:
    """Les couleurs de ``ring-offset-`` du fichier.

    ``ring-offset-2`` (une LARGEUR) ne matche pas — le motif exige une
    initiale alphabétique. Et la lecture passe par les CHAÎNES DE SLOTS,
    pas par la source : sinon la gate lit les commentaires, et rougissait
    sur celui qui explique la faute qu'elle interdit (vécu le 2026-08-15,
    dans le fichier même où elle venait d'être corrigée).
    """
    return {
        colour
        for _slot, classes in theme_slot_strings(source)
        for colour in _RING_OFFSET_COLOR.findall(classes)
    }


_CASES = [
    (theme, surface)
    for theme in _THEMES
    if (surface := _root_surface(theme.text)) is not None
]


def test_sweep_is_not_vacuous() -> None:
    """Au moins deux conteneurs à surface doivent être VUS.

    Le plancher lit la DÉCOUVERTE (combien de thèmes ``_root_surface``
    reconnaît), pas la population de fichiers : si la lecture du slot
    ``root`` cesse d'aboutir — thème reformaté, slot renommé, extracteur
    AST cassé — la liste tombe à zéro et la gate passerait au vert en ne
    testant rien. Mesuré le 2026-08-15 : 2 (navbar, sidebar).
    """
    assert len(_CASES) >= 2, (
        f"Le balayage ne reconnaît plus que {len(_CASES)} thème(s) dont le "
        f"slot ``root`` peint une surface : "
        f"{[t.path.parent.name for t, _ in _CASES]}. "
        "Le parseur de slot ``root`` a probablement cessé de matcher — la "
        "gate ne teste plus rien."
    )


@pytest.mark.parametrize(
    "theme,surface", _CASES, ids=[t.path.parent.name for t, _ in _CASES]
)
def test_ring_offset_matches_its_surface(theme: ParsedSource, surface: str) -> None:
    wrong = _offset_colors(theme.text) - {surface}
    assert not wrong, (
        f"{theme.path.parent.name} : son slot ``root`` peint ``bg-{surface}``, "
        f"mais un anneau de focus du même fichier pose son écart en "
        f"{sorted('ring-offset-' + c for c in wrong)}.\n"
        f"L'écart est PEINT : d'une autre couleur que la surface, il "
        f"dessine un liseré autour de l'élément focalisé au lieu de "
        f"disparaître. Utilise ``ring-offset-{surface}``, ou "
        f"``ring-inset`` si le composant n'a pas d'aplat actif (cf. "
        f"``bottom_bar``)."
    )


def test_the_detector_still_bites() -> None:
    """Mutation : la surface et l'écart d'anneau sont encore lus.

    L'écart est PEINT : d'une autre couleur que la surface, il dessine
    un liseré autour de l'élément focalisé au lieu de disparaître. Si
    l'une des deux regex cessait de matcher, la comparaison porterait
    sur du vide.
    """
    assert _BG.search("rounded-md bg-surface p-2").group(1) == "surface"
    assert not _BG.search("hover:bg-surface-2"), "faux positif"
    assert _RING_OFFSET_COLOR.search("ring-offset-surface").group(1) == "surface"
    assert not _RING_OFFSET_COLOR.search("ring-offset-2"), "faux positif"
