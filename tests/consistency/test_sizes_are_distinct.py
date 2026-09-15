"""Deux ``size=`` différents ne rendent pas les mêmes classes.

Un composant qui expose ``size="sm" | "md" | "lg"`` promet trois tailles.
Si deux d'entre elles composent la même chaîne de classes, la prop est un
mensonge : l'utilisateur change la valeur, rien ne bouge, et rien ne le
signale.

Comment ce trou a été trouvé (audit de mutation, 2026-07-29)
-------------------------------------------------------------
``creating-a-component.md`` annonçait que ``test_size_reaches_slots``
vérifiait « chaque ``size=`` produit des classes distinctes ». En écrivant
la mutation censée la faire rougir — rendre ``xl`` identique à ``sm`` dans
la table de Button — la gate est restée **verte**.

Elle allait bien : elle vérifie tout autre chose, qu'aucun slot HORS de la
table ``sizes`` ne gèle une utilitaire de taille. C'est **la doc du funnel
qui mentait** sur ce qu'elle garde. Trois specs de mutation successifs ont
été écrits contre la mauvaise cible avant que ça saute aux yeux.

L'invariant tenait quand même — les 5 tailles de Button sont distinctes. Il
n'était simplement gardé par rien. C'est le pire état : vrai, cru gaté, et
libre de dériver au prochain refactor de thème.

⚠️ Ce qu'on compare
--------------------
Les classes **de dimension** uniquement (``h-``, ``w-``, ``px-``, ``py-``,
``p-``, ``text-``, ``gap-``, ``size-``). Deux tailles peuvent légitimement
partager leur couleur, leur bordure ou leur transition — ce n'est pas ce
que ``size=`` promet de changer.
"""

from __future__ import annotations

import re

import pytest

from bretzel.components.base import SIZE_SCALE
from bretzel.components.base.testing import render_isolated
from bretzel.core.serialize import serialize
from tests.audit.test_binding_completeness import CONSTRUCT, _Skip
from tests.consistency._discovery import public_component_classes

# Préfixes d'utilitaires Tailwind qui portent une DIMENSION. Le reste
# (couleurs, bordures, transitions) peut coïncider entre deux tailles sans
# que ce soit un défaut.
_DIMENSIONAL = ("h-", "w-", "px-", "py-", "p-", "text-", "gap-", "size-",
                "min-h-", "min-w-", "max-h-", "max-w-", "leading-")


def _is_class_valued(sizes: dict) -> bool:
    """La table exprime-t-elle ses tailles en CLASSES CSS ?

    ⚠️ La table ``sizes`` porte **quatre types** dans ce dépôt, et ils ne
    doivent pas converger (décision actée) :

    a) des classes Tailwind pour un slot — ``"h-10 px-4 text-sm"`` ;
    b) un token de taille pour un ENFANT — ``icon_size="md"`` ;
    c) des **numériques SVG** — ``{"h": 280, "stroke": 1.5}`` chez les
       4 charts et Tree ;
    d) des scalaires de layout.

    Seul (a) se compare en classes. Les charts rendent leur taille en
    ATTRIBUTS SVG (``height="280"``), invisible à un diff de ``class=`` —
    les inclure produisait 14 faux positifs au premier run.
    """
    values = list(sizes.values())
    if not values:
        return False
    flat = []
    for v in values:
        if isinstance(v, dict):
            flat.extend(v.values())
        else:
            flat.append(v)
    # Au moins une valeur textuelle qui ressemble à une classe utilitaire.
    return any(
        isinstance(x, str) and x.startswith(_DIMENSIONAL) for x in flat
    )


# Les noms de taille du design system. Une table dont les clés sortent de
# cet ensemble est une table INVERSÉE — ``sizes[<slot>][<size>]`` — que
# ``test_size_reaches_slots::test_size_table_shape_is_canonical`` xfail
# déjà. FileUpload et les deux date-pickers sont dans ce cas : leurs clés
# sont ``button_icon_size``, ``dropzone_padding``… Les traiter comme des
# noms de taille faisait passer ``size="button_icon_size"`` au
# constructeur — du non-sens, et 3 faux positifs.
#: L'échelle de contrôle plus ``2xl`` : ``Avatar`` l'étend (visuel
#: portrait) et ce balayage touche aussi les tables typographiques. Le
#: socle porte le noyau ; l'extension est déclarée ICI parce qu'elle est
#: propre à ce test, pas à la grammaire des contrôles.
_SIZE_NAMES = frozenset(SIZE_SCALE) | {"2xl"}


def _sized() -> list[type]:
    """Composants dont le thème exprime ≥ 2 tailles EN CLASSES, dans la
    forme canonique ``sizes[<size>][<slot>]``."""
    out = []
    for cls in public_component_classes():
        sizes = (getattr(cls, "THEME", {}) or {}).get("sizes") or {}
        if not (isinstance(sizes, dict) and len(sizes) >= 2):
            continue
        if not set(sizes).issubset(_SIZE_NAMES):
            continue  # table inversée — hors périmètre
        if _is_class_valued(sizes):
            out.append(cls)
    return out


_SIZED = _sized()


def _dimension_classes(cls: type, size: str) -> frozenset[str] | None:
    builder = CONSTRUCT.get(cls.__name__)
    try:
        with render_isolated():
            node = (
                builder(cls, "size", size) if builder else cls(size=size)
            ).render()
            html = serialize(node)
    except (_Skip, Exception):
        # Abstention de CONSTRUCTION. Elle est déclarée dans
        # ``_CANNOT_BUILD`` — vide aujourd'hui — parce qu'un composant
        # qui cesse de se monter sortirait sinon du balayage sans un mot.
        return None
    # ⚠️ TOUS les ``class=`` du rendu, pas seulement celui de la root.
    #
    # La première version ne lisait que la root et accusait 25 composants
    # sur 37. Elle avait tort : chez la plupart, ``size=`` ne touche PAS la
    # root mais un slot interne — la root de ``Switch`` est identique en
    # ``sm`` et en ``lg``, la taille vit sur la piste et le curseur.
    #
    # Une gate qui accuse les deux tiers du catalogue au premier run a plus
    # de chances d'être fausse que le catalogue.
    classes = re.findall(r'\sclass="([^"]*)"', html)
    if not classes:
        return None
    return frozenset(
        t
        for chunk in classes
        for t in chunk.split()
        if t.startswith(_DIMENSIONAL)
    )


def test_the_gate_has_a_population() -> None:
    """Plancher de non-vacuité."""
    assert len(_SIZED) >= 20, (
        f"seulement {len(_SIZED)} composants déclarent une table `sizes` "
        f"à 2 entrées ou plus (28 mesurés le 2026-07-29) — la découverte "
        f"a régressé."
    )


@pytest.mark.parametrize("cls", _SIZED, ids=lambda c: c.__name__)
def test_each_size_renders_distinct_dimensions(cls: type) -> None:
    sizes = sorted((getattr(cls, "THEME", {}) or {}).get("sizes") or {})
    rendered: dict[str, frozenset[str]] = {}
    for size in sizes:
        got = _dimension_classes(cls, size)
        if got is not None:
            rendered[size] = got

    if len(rendered) < 2:
        pytest.skip(f"{cls.__name__} : moins de 2 tailles rendues nues")

    # ⚠️ Le rendu EXERCE-T-IL la table ? Un ``Tabs`` sans onglets, un
    # ``Table`` sans lignes, un ``EmptyState`` nu : les slots dimensionnés
    # ne se matérialisent jamais, donc les cinq tailles rendent
    # légitimement la même chose. Ce n'est pas une collision, c'est une
    # construction qui ne va pas jusqu'au slot.
    #
    # C'est le même artefact qui avait produit le « 36/76 composants
    # perdent slots= » de l'audit — un chiffre mesuré sur des constructions
    # nues, et faux.
    table = (getattr(cls, "THEME", {}) or {}).get("sizes") or {}
    declared_tokens = {
        tok
        for value in table.values()
        for chunk in ([value] if isinstance(value, str) else
                      [v for v in value.values() if isinstance(v, str)]
                      if isinstance(value, dict) else [])
        for tok in chunk.split()
        if tok.startswith(_DIMENSIONAL)
    }
    seen = set().union(*rendered.values())
    if declared_tokens and not (declared_tokens & seen):
        pytest.skip(
            f"{cls.__name__} : construit nu, aucun slot dimensionné n'est "
            f"rendu — la table n'est pas exercée, la comparaison ne "
            f"prouverait rien"
        )

    collisions = [
        (a, b)
        for i, a in enumerate(sorted(rendered))
        for b in sorted(rendered)[i + 1:]
        if rendered[a] == rendered[b]
    ]
    assert not collisions, (
        f"{cls.__name__} : ces paires de tailles rendent les MÊMES classes "
        f"de dimension — {collisions}.\n"
        f"  `size=` promet de changer quelque chose ; ici l'utilisateur "
        f"change la valeur et rien ne bouge, sans le moindre signal.\n"
        f"  Exemple mesuré pour {sorted(rendered)[0]!r} : "
        f"{sorted(rendered[sorted(rendered)[0]])}"
    )


#: Ce que la sonde ``size=`` ne construit pas, avec sa raison.
#: **VIDE**, et mesuré le 2026-08-19 : les 34 composants dimensionnés se
#: montent tous, sur les cinq paliers. L'``except`` qui vit plus haut ne
#: rattrapait donc plus rien — mais rien ne le disait, et le jour où il
#: aurait rattrapé quelque chose, personne ne l'aurait su non plus.
_CANNOT_BUILD: dict[str, str] = {}


def size_probe_abstentions() -> dict[str, str]:
    """``Classe -> paliers`` que la sonde ``size=`` ne monte pas."""
    out: dict[str, str] = {}
    for cls in _SIZED:
        failed = []
        for size in sorted((getattr(cls, "THEME", {}) or {}).get("sizes") or {}):
            builder = CONSTRUCT.get(cls.__name__)
            try:
                with render_isolated():
                    (
                        builder(cls, "size", size) if builder
                        else cls(size=size)
                    ).render()
            except Exception:
                failed.append(size)
        if failed:
            out[cls.__name__] = ", ".join(failed)
    return out


def test_the_abstentions_are_declared() -> None:
    """Ce que la sonde ``size=`` ne monte pas est NOMMÉ, pas compté.

    La table est vide aujourd'hui, et c'est le but : une exemption se
    déclare avec sa raison, elle ne s'obtient pas en échouant en silence.
    """
    measured = size_probe_abstentions()
    surprise = sorted(set(measured) - set(_CANNOT_BUILD))
    assert not surprise, (
        f"{ {k: measured[k] for k in surprise} } ne se monte(nt) plus sous "
        f"la sonde `size=` : ils sortent du balayage EN SILENCE, et la "
        f"règle « deux paliers rendent des dimensions distinctes » ne les "
        f"juge plus."
    )
    stale = sorted(set(_CANNOT_BUILD) - set(measured))
    assert not stale, (
        f"{stale} se monte(nt) de nouveau — retire l'entrée."
    )
