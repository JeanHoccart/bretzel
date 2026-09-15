"""Gate — un CONTENEUR qui peint un fond opaque déclare son avant-plan.

Le défaut qu'elle ferme (finding [3], mesuré le 2026-08-19)
-----------------------------------------------------------
``ui.card(color="primary")`` posait ``bg-primary`` sur sa racine et
**rien** pour le texte. Le contenu gardait donc la couleur héritée de la
page — mesuré : fond teal, texte ``rgb(15, 23, 42)``. Illisible. C'est ce
qui privait la liste sélectionnable de l'écran contacts du CRM de son
signal fort : la carte « active » était peinte, et devenue impossible à
lire.

La convention existait pourtant, et le thème de la carte s'en servait
déjà — **à un slot près** : son slot ``hoverable`` écrit
``hover:border-{fg_color}/50``. Le couple ``<couleur>`` /
``<couleur>-foreground`` est tenu par Badge, Button et IconButton. La
carte était la seule SURFACE du catalogue à ne peindre que la moitié.

La population, et pourquoi c'est celle-là
------------------------------------------
Pas « tout ce qui porte ``bg-{bg_color}`` » : la moitié du catalogue
peint des TEINTES (``bg-{bg_color}/15``, un fond à 15 % au-dessus de la
page) qu'on associe volontairement à ``text-{bg_color}`` — c'est le style
« soft », et il est juste. Pas non plus les décorations opaques : un point
de légende ``size-3``, une barre de progression, une poignée de slider,
la flèche d'un tooltip. Aucune ne portera jamais de texte, et leur coller
un avant-plan ajouterait une classe morte.

Ce qui reste est exactement la bonne population : les composants
**conteneurs** (``IS_CONTAINER``) qui acceptent ``color=`` — ceux dont la
raison d'être est d'héberger du contenu. Mesuré le 2026-08-21 : 17
l'acceptent, et **un seul** peint un fond opaque. C'était la carte.

Ce que la gate n'affirme pas
-----------------------------
Que le contraste soit suffisant — ça, c'est une propriété de la palette,
pas du thème du composant. Elle ferme la classe : *une surface qui peint
son fond sans dire ce qu'on écrit dessus.*
"""

from __future__ import annotations

import functools
import re

import pytest

from bretzel.components.base.attrs import ComponentUsageError
from tests.consistency._discovery import (
    public_component_classes,
    rendered_html_of,
    ui_name_of,
)

#: La couleur-sonde. N'importe laquelle de la palette ferait l'affaire ;
#: celle-ci a un ``-foreground`` très contrasté, donc l'oubli se voit.
_PROBE = "primary"

#: Un fond **OPAQUE** : ``bg-primary``, jamais ``bg-primary/15`` (une
#: teinte, qui se marie légitimement à ``text-primary``) ni
#: ``bg-primary-foreground``.
_OPAQUE_BG = re.compile(rf"(?<![\w/-])bg-{_PROBE}(?![\w/-])")

#: Le plancher : le catalogue compte 17 conteneurs qui acceptent
#: ``color=`` au 2026-08-21. Un seuil, pas le compte exact — mais assez
#: haut pour qu'une construction cassée en masse rougisse.
_COLOURABLE_FLOOR = 12

#: Les conteneurs qui REFUSENT ``color=`` — nommés un par un, pas
#: comptés. Un plafond chiffré laisserait passer « un qui sort, un qui
#: rentre » : le jour où ``ui.card`` cesserait de lire ``color`` pendant
#: qu'un autre se met à le lire, le compte tiendrait et la carte serait
#: sortie du balayage sans un mot.
#:
#: Le refus est DÉFINITIONNEL, pas un accident : ce sont les conteneurs
#: de mise en page (``vstack``, ``grid``, ``flex``…), les coques
#: (``dialog``, ``drawer``, ``sidebar``…) et les sous-parties d'un
#: composant coloré par son parent (``accordion_item``, ``tab_panel``).
#: Aucun ne peint de fond, donc aucun n'a d'avant-plan à déclarer.
_REFUSES_COLOUR: frozenset[str] = frozenset({
    "accordion_item", "bottom_bar", "container", "dialog", "drawer",
    "dropdown", "flex", "form", "form_field", "fragment", "grid",
    "hstack", "navbar", "navbar_section", "outlet", "pane", "popover",
    "resizable_panel", "sidebar", "sidebar_section", "step_panel",
    "tab_panel", "tree_node", "viewport", "vstack",
})

#: Ceux que la table de construction partagée DÉCLARE hors banc — ils
#: exigent un contexte qu'un banc ne fabrique pas (``ui.link`` veut une
#: route). ``rendered_html_of`` rend ``None`` pour eux, et pour eux seuls.
_NEEDS_CONTEXT: frozenset[str] = frozenset({"link"})


@functools.cache
def _container_classes() -> tuple[type, ...]:
    return tuple(
        cls for cls in public_component_classes()
        if getattr(cls, "IS_CONTAINER", False)
    )


def _root_html(cls: type) -> str | None:
    """Le HTML du conteneur sondé avec ``color=``, ou ``None`` s'il s'abstient.

    Le refus est LU, jamais avalé : un composant qui ne déclare pas
    ``color`` lève ``ComponentUsageError`` (le socle refuse le kwarg
    mort), et ``ui.fragment`` lève ``TypeError`` — il n'a aucun élément où
    poser quoi que ce soit. Ces deux-là sont des RÉPONSES.

    **Toute autre exception remonte**, et c'est elle qui empêche un
    composant de sortir du balayage sans que personne ne le sache. Qui
    s'abstient est nommé dans ``_REFUSES_COLOUR`` / ``_NEEDS_CONTEXT``,
    et ``test_the_abstentions_are_declared`` refuse les DEUX écarts.
    """
    try:
        return rendered_html_of(cls, prop="color", value=_PROBE)
    except (ComponentUsageError, TypeError):
        return None


@functools.cache
def colourable_containers() -> tuple[tuple[str, str], ...]:
    """``(nom ui, classes de la racine)`` des conteneurs qui lisent ``color=``.

    Le refus est LU, pas avalé : un composant qui ne déclare pas ``color``
    lève ``ComponentUsageError`` (le socle refuse le kwarg mort), et
    ``ui.fragment`` lève ``TypeError`` parce qu'il n'a aucun élément où
    poser quoi que ce soit. Ces deux-là sont des réponses, pas des
    pannes. **Toute autre exception remonte** — c'est elle qui empêche un
    composant de sortir du balayage sans que personne ne le sache
    (``test_no_gate_swallows_a_component``).
    """
    found: list[tuple[str, str]] = []
    for cls in _container_classes():
        html = _root_html(cls)
        if not html:
            continue
        root = re.match(r"<[\w-]+[^>]*>", html)
        if root is None:
            continue
        klass = re.search(r'class="([^"]*)"', root.group(0))
        found.append((ui_name_of(cls), klass.group(1) if klass else ""))
    return tuple(found)


def opaque_surfaces() -> list[tuple[str, str]]:
    return [
        (name, klass) for name, klass in colourable_containers()
        if _OPAQUE_BG.search(klass)
    ]


# ───────────────────────────────────────────────────────────────────────
# Le plancher
# ───────────────────────────────────────────────────────────────────────


def test_the_sweep_builds_the_containers() -> None:
    built = colourable_containers()
    assert len(built) >= _COLOURABLE_FLOOR, (
        f"seulement {len(built)} conteneur(s) acceptent `color=` — il y en "
        f"avait 17 le 2026-08-21. La construction échoue en masse, ou "
        f"`IS_CONTAINER` ne se lit plus : la gate ne balaie plus rien."
    )


def test_the_abstentions_are_declared() -> None:
    """Qui sort du balayage est NOMMÉ, et la table ne pourrit pas.

    Les deux écarts rougissent : un conteneur qui s'abstient sans être
    déclaré (il disparaîtrait en silence), et une entrée déclarée qui ne
    s'abstient plus (la table autoriserait plus que la réalité).

    Un plafond chiffré ne suffirait pas — il laisse passer « un qui sort,
    un qui rentre », qui est exactement la façon dont ``ui.card`` pourrait
    quitter cette gate sans qu'elle bouge d'un test.
    """
    abstained = {
        ui_name_of(cls) for cls in _container_classes()
        if _root_html(cls) is None
    }
    declared = _REFUSES_COLOUR | _NEEDS_CONTEXT

    undeclared = sorted(abstained - declared)
    assert not undeclared, (
        f"ces conteneurs sortent du balayage sans être déclarés : "
        f"{undeclared}. Soit ils ne lisent pas `color=` (ajoute-les à "
        f"`_REFUSES_COLOUR`), soit leur construction casse — et dans ce "
        f"second cas c'est un bug, pas une exemption."
    )
    stale = sorted(declared - abstained)
    assert not stale, (
        f"ces entrées sont déclarées abstentionnistes mais se construisent "
        f"désormais : {stale}. Retire-les — une table qui garde des noms "
        f"périmés autorise plus que la réalité, et c'est par là qu'un "
        f"composant repart en silence."
    )


# ───────────────────────────────────────────────────────────────────────
# L'interdiction
# ───────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "case", colourable_containers(), ids=lambda c: c[0]
)
def test_an_opaque_surface_declares_its_foreground(
    case: tuple[str, str],
) -> None:
    name, klass = case
    if not _OPAQUE_BG.search(klass):
        pytest.skip("pas de fond opaque coloré — rien à apparier")
    assert f"text-{_PROBE}-foreground" in klass, (
        f"ui.{name}(color=…) peint `bg-{_PROBE}` sur sa racine sans "
        f"`text-{{fg_color}}` : le contenu garde la couleur héritée de la "
        f"page, et la surface devient illisible dès que la couleur est "
        f"sombre (mesuré : fond teal, texte rgb(15, 23, 42)).\n"
        f"  La convention est `<couleur>` / `<couleur>-foreground`, et "
        f"Badge / Button / IconButton la tiennent déjà. Ajoute "
        f"`text-{{fg_color}}` au slot qui pose `bg-{{bg_color}}`.\n"
        f"  classes : {klass}"
    )


# ───────────────────────────────────────────────────────────────────────
# La preuve que le détecteur mord
# ───────────────────────────────────────────────────────────────────────


def test_the_detector_still_bites() -> None:
    """Le fond opaque, la teinte, et le faux ami ``-foreground``."""
    assert _OPAQUE_BG.search("rounded-xl bg-primary border"), (
        "le détecteur ne reconnaît plus un fond opaque — il resterait "
        "vert sur un catalogue entier de surfaces à moitié peintes."
    )
    # Une TEINTE n'est pas un fond opaque : elle se marie à
    # ``text-{bg_color}``, et l'exiger d'elle serait un faux positif sur
    # la moitié du catalogue (Badge, Alert, Avatar, Navbar…).
    assert not _OPAQUE_BG.search("bg-primary/15 text-primary")
    # Et ``bg-primary-foreground`` n'est pas ``bg-primary``.
    assert not _OPAQUE_BG.search("bg-primary-foreground")


def test_a_known_pair_is_still_recognised() -> None:
    """Le contrôle POSITIF : la forme réparée passe bien la règle.

    Un détecteur qui refuserait aussi la solution serait aveugle dans
    l'autre sens — la gate rougirait sans qu'aucun fix ne la calme.
    """
    fixed = "rounded-xl bg-primary text-primary-foreground border"
    assert _OPAQUE_BG.search(fixed)
    assert f"text-{_PROBE}-foreground" in fixed
