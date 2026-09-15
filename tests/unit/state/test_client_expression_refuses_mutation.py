"""Une ``ClientExpression`` refuse les mutateurs qu'elle hérite.

Le défaut qu'ils ouvraient
--------------------------
``ClientExpression`` hérite de ``ClientBinding``, donc de ``.set()``,
``.toggle()``, ``.push()``… Appliqués à une expression, ils composaient du
JS **invalide** en silence ::

    (state.a | state.b).set(3)   ->   ($bz.state.…a || $bz.state.…b) = 3

``SyntaxError`` au bind navigateur, zéro signal côté Python, et rien dans
le HTML qui l'annonce. ``Component`` gardait déjà l'autre porte — passer
une expression à une prop à double sens — mais la même erreur entrait par
celle-ci.

Une expression est une LECTURE : il n'existe aucune cible à laquelle
assigner. Le refus ne coûte rien au rendu, il ne se déclenche qu'en cas
de mésusage.
"""

from __future__ import annotations

import pytest

from bretzel.state.scopes.client import (
    ClientBinding,
    ClientExpression,
    ReactivityError,
)

#: Les six mutateurs hérités, avec un argument plausible pour chacun.
_MUTATEURS = [
    ("toggle", ()),
    ("increment", ()),
    ("decrement", ()),
    ("set", (3,)),
    ("push", ("x",)),
    ("clear", ()),
]


def _binding() -> ClientBinding:
    return ClientBinding(
        class_name="UI", instance_key="default", field_name="champ", value=1
    )


@pytest.mark.parametrize(("nom", "args"), _MUTATEURS, ids=[m for m, _ in _MUTATEURS])
def test_an_expression_refuses_every_mutator(nom: str, args: tuple) -> None:
    expr = ClientExpression("($a || $b)")
    with pytest.raises(ReactivityError) as leve:
        getattr(expr, nom)(*args)
    message = str(leve.value)
    assert nom in message, "le message doit nommer le mutateur appelé"
    assert "state.champ" in message or "state." in message, (
        "le message doit indiquer la sortie : appeler sur le CHAMP"
    )


@pytest.mark.parametrize(("nom", "args"), _MUTATEURS, ids=[m for m, _ in _MUTATEURS])
def test_a_plain_binding_still_mutates(nom: str, args: tuple) -> None:
    """Le versant LICITE — sans lui, refuser TOUT passerait aussi bien.

    C'est le jumeau qui prouve que le refus vise l'expression et pas la
    famille entière : sur un champ, les six rendent toujours leur source JS.
    """
    js = getattr(_binding(), nom)(*args)
    assert isinstance(js, str) and "$bz.state.UI.default.champ" in js


def test_an_expression_is_still_readable() -> None:
    """Refuser d'écrire ne doit pas casser la lecture, qui est son métier."""
    expr = ClientExpression("($a || $b)")
    assert expr.binding_path() == "($a || $b)"
    assert expr.serialize_path() == "($a || $b)"
    # L'algèbre continue de composer — le refus ne touche que les mutateurs.
    assert isinstance(~expr, ClientExpression)
