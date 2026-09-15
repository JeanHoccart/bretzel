"""Gate — l'espace entre enfants s'écrit d'UNE façon dans tout le catalogue.

Le défaut qu'elle ferme (2026-08-23)
--------------------------------------
``ui.resizable`` est un conteneur flex — sa racine vaut ``flex w-full``,
exactement comme ``ui.flex`` — et il n'exposait pas ``gap``. On écrivait
donc ``ui.hstack(gap="md")`` d'un côté et ``ui.resizable(classes="gap-4")``
de l'autre : **même CSS, deux écritures**, ce que le principe 4 du
charter interdit.

Le symptôme qui l'a fait remonter n'y ressemblait pas : « l'espacement au
niveau de resizable n'existe pas ». Mesuré sur la coque du CRM (parent en
``p-8``), le panneau commençait bien à x=32 — le padding de l'ancêtre
l'atteignait. Mais son contenu courait jusqu'à 384, où la poignée
commence. Zéro. **Le padding d'un ancêtre ne peut jamais créer d'espace À
L'INTÉRIEUR du groupe** ; seul le parent des panneaux sait où est la
poignée, et le nom de ce métier est ``gap``.

Les deux invariants
--------------------
1. **Les tables ``gaps`` sont identiques, cran par cran.** Elles sont
   RECOPIÉES d'un thème à l'autre et non partagées — c'est la convention
   du dépôt (un thème reste self-contained, cf. la mémoire
   ``feedback_no_shared_style_tokens``). Une convention recopiée dérive ;
   celle-ci est donc gatée plutôt que factorisée.
2. **La table et la prop vont par paire.** Une table sans prop est du
   thème mort ; une prop sans table rendrait la chaîne vide en silence —
   le composant accepterait ``gap="md"`` et n'espacerait rien.

Ce qu'elle n'affirme PAS
-------------------------
Que tout conteneur flex DOIVE exposer ``gap``. Beaucoup de composants ont
une racine ``inline-flex`` pour aligner leur propre décor (``ui.button``
et son icône) : ce ne sont pas des conteneurs de mise en page, et leur
espacement intérieur est une décision de thème, pas une prop. La
population est donc « qui a déjà une table », pas « qui est flex ».
"""

from __future__ import annotations

import inspect

import pytest

from tests.consistency._discovery import public_component_classes, ui_name_of

#: L'échelle de référence — six crans, la même partout. Écrite ici en
#: toutes lettres et non importée d'un thème : une gate qui lirait la
#: table du framework resterait verte si on la vidait.
_SCALE = {
    "none": "gap-0",
    "xs": "gap-1",
    "sm": "gap-2",
    "md": "gap-4",
    "lg": "gap-6",
    "xl": "gap-8",
}

#: Le plancher, mesuré le 2026-08-23 : flex, hstack, vstack (les deux
#: héritent du thème de Flex), grid, carousel, resizable.
_FAMILY_FLOOR = 6


def _theme_of(cls: type) -> dict:
    theme = getattr(cls, "THEME", None)
    return theme if isinstance(theme, dict) else {}


def with_a_gaps_table() -> list[type]:
    return [c for c in public_component_classes() if "gaps" in _theme_of(c)]


def exposing_gap() -> list[type]:
    out = []
    for cls in public_component_classes():
        try:
            params = inspect.signature(cls.__init__).parameters
        except (TypeError, ValueError):  # pragma: no cover — builtin __init__
            continue
        if "gap" in params:
            out.append(cls)
    return out


def test_the_family_is_not_vacuous() -> None:
    """① Le plancher, lu sur LA découverte de cette gate."""
    seen = with_a_gaps_table()
    assert len(seen) >= _FAMILY_FLOOR, (
        f"seulement {len(seen)} composants portent une table `gaps` "
        f"({_FAMILY_FLOOR} le 2026-08-23) : la découverte est cassée, et "
        f"la comparaison ne porterait plus sur rien."
    )


@pytest.mark.parametrize(
    "cls", with_a_gaps_table(), ids=lambda c: ui_name_of(c)
)
def test_the_scale_is_the_same_everywhere(cls: type) -> None:
    """② Six crans, les mêmes classes, partout."""
    table = _theme_of(cls)["gaps"]
    assert table == _SCALE, (
        f"la table `gaps` de ui.{ui_name_of(cls)} a dérivé :\n"
        f"  lue     : {table}\n"
        f"  attendue: {_SCALE}\n"
        f"Elles sont RECOPIÉES d'un thème à l'autre (un thème reste "
        f"self-contained), donc rien d'autre que cette gate ne les tient "
        f"ensemble. Si l'échelle doit bouger, elle bouge partout — et "
        f"`_SCALE` avec, dans le même commit."
    )


def test_a_table_and_its_prop_go_together() -> None:
    """② bis — l'un sans l'autre est mort ou muet."""
    tabled = {ui_name_of(c) for c in with_a_gaps_table()}
    propped = {ui_name_of(c) for c in exposing_gap()}
    assert tabled == propped, (
        f"table `gaps` et prop `gap=` ne vont plus par paire.\n"
        f"  table sans prop : {sorted(tabled - propped)} — du thème mort, "
        f"que personne ne peut atteindre.\n"
        f"  prop sans table : {sorted(propped - tabled)} — le composant "
        f"accepte `gap=\"md\"` et rend une classe VIDE, sans rien dire."
    )


def test_the_comparison_still_bites() -> None:
    """③ La mutation, dans les deux sens.

    Le versant licite compte autant : une comparaison qui accepterait
    n'importe quel sur-ensemble laisserait passer un cran ajouté à un
    seul thème — la dérive exacte qu'on garde.
    """
    assert _SCALE != {**_SCALE, "md": "gap-3"}, "un cran changé doit mordre"
    assert {k: v for k, v in _SCALE.items() if k != "xl"} != _SCALE, (
        "un cran retiré doit mordre"
    )
    assert _SCALE != {**_SCALE, "xxl": "gap-12"}, "un cran ajouté doit mordre"
    assert dict(_SCALE) == _SCALE, "une table identique doit être épargnée"
