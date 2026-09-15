"""``grow=`` — le PARENT distribue l'axe principal à ses enfants.

Le manque que la prop ferme (finding [30]). La racine de tous les
contrôles porte ``w-full``, et c'est la bonne convention : un champ
remplit sa colonne. Mais dans un ``wrap=True``, un item dont la base vaut
100 % ne peut jamais partager sa ligne — la barre devient une PILE.
Mesuré en Chromium le 2026-08-25 : deux champs dans 860 px rendaient
860 px chacun et une barre de 148 px, contre 422 px chacun et 66 px avec
``grow="16rem"``. Trois apps portaient la même rustine à l'appel
(``BAR_FIELD = "basis-64 grow"``).

Ce qui se juge ici : la table, les refus, et ce qui part sur le fil. Le
versant navigateur — que la barre reste une BARRE et que la pile
disparaisse vraiment — est dans ``tests/probes/probe_flex_grow.py`` : ces
classes ne produisent aucune différence de HTML mesurable, seulement des
pixels.
"""

from __future__ import annotations

import pytest

from bretzel.components.base.attrs import ComponentUsageError
from bretzel.components.base.testing import render_isolated
from bretzel.components.layout.flex import Flex
from bretzel.components.layout.pane import Pane
from bretzel.components.layout.stack import HStack
from bretzel.components.layout.viewport import Viewport
from bretzel.core.serialize import serialize


def classes(build) -> str:
    """Le composant est bâti DANS le contexte, jamais avant.

    ``Component.__init__`` appelle ``current_context()`` : construire
    l'argument avant d'entrer dans ``render_isolated`` lève, et le
    message parle du contexte au lieu de la prop qu'on teste.
    """
    with render_isolated():
        return serialize(build().render())


# ── Ce qui part sur le fil ────────────────────────────────────────────

def test_nothing_asked_emits_nothing() -> None:
    """Load-bearing : c'est ce qui empêche la prop de peser sur les
    centaines de piles du dépôt qui ne la demandent pas."""
    out = classes(lambda: HStack())
    assert "*:grow" not in out
    assert "*:basis" not in out


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (True, "*:grow *:basis-0"),
        ("equal", "*:grow *:basis-0"),
        ("12rem", "*:grow *:basis-48"),
        ("16rem", "*:grow *:basis-64"),
        ("20rem", "*:grow *:basis-80"),
    ],
)
def test_each_base_reaches_the_class(value, expected: str) -> None:
    assert expected in classes(lambda: HStack(grow=value))


def test_true_is_an_alias_of_equal() -> None:
    """Et pas une cinquième clé : une table indexée par des types mêlés
    ferait afficher ``True`` au milieu de trois longueurs dans
    ``bretzel describe flex``."""
    assert classes(lambda: HStack(grow=True)) == classes(lambda: HStack(grow="equal"))


def test_the_parent_carries_it_alone() -> None:
    """Aucun enfant n'est touché — c'est ce qui fait marcher la prop avec
    les 46 composants du catalogue qui ne déclarent aucune largeur."""
    from bretzel.components.primitives.text import Text

    with render_isolated():
        stack = HStack(grow="16rem")
        with stack:
            Text("un")
            Text("deux")
        out = serialize(stack.render())
    assert out.count("*:basis-64") == 1
    assert "basis-64" not in out.split("</div>")[0].split(">", 1)[1]


def test_it_composes_with_wrap() -> None:
    """Les deux ensemble sont le cas réel : c'est ``wrap`` qui crée le
    besoin, donc la prop ne servirait à rien si elle l'excluait."""
    out = classes(lambda: HStack(wrap=True, grow="16rem"))
    assert "flex-wrap" in out and "*:basis-64" in out


# ── Les refus ─────────────────────────────────────────────────────────

def test_a_base_outside_the_table_raises() -> None:
    """Une valeur hors table rendrait la chaîne vide — donc un appel qui
    ne fait RIEN, avec un HTML valide et la barre toujours empilée. C'est
    le kwarg mort, mode d'échec dominant du dépôt.

    ⚠️ ``grow`` est pour l'instant la SEULE des six props de Flex à
    refuser : ``align="stretchy"`` rend encore la chaîne vide en silence.
    L'étendre aux cinq autres est un changement de comportement, donc un
    geste à part — noté dans ``work/todo.md``.
    """
    with pytest.raises(ComponentUsageError, match="16rem"):
        classes(lambda: HStack(grow="15rem"))


def test_the_refusal_names_the_accepted_values() -> None:
    with pytest.raises(ComponentUsageError) as caught:
        classes(lambda: HStack(grow="wide"))
    message = str(caught.value)
    assert "'equal'" in message and "classes=" in message


def test_a_breakpoint_dict_raises() -> None:
    """``grow`` n'est pas gradué : sans ce refus, le dict atteindrait le
    ``dict.get`` d'une table et mourrait sur ``unhashable type``, qui ne
    dit rien de la vraie faute.

    ⚠️ Le refus vient du SOCLE depuis le 2026-09-04, plus de
    ``Flex._grow_class`` — il vaut donc pour tous les composants, et son
    message nomme la classe en plus du prop.
    """
    with pytest.raises(ComponentUsageError, match="dict de paliers"):
        classes(lambda: HStack(grow={"base": "16rem"}))


def test_false_is_treated_as_not_asked() -> None:
    """``grow=False`` doit se comporter comme l'absence, pas lever : un
    appelant qui calcule la valeur (``grow=is_bar``) écrit exactement ça."""
    assert classes(lambda: HStack(grow=False)) == classes(lambda: HStack())


# ── La famille entière, pas seulement hstack ──────────────────────────

@pytest.mark.parametrize("cls", [Flex, HStack, Viewport, Pane])
def test_every_family_member_resolves_it(cls: type) -> None:
    """Le défaut que la gate garde, vérifié ici sur le rendu réel :
    ``ui.pane`` et ``ui.viewport`` ont chacun leur THEME, donc la table
    peut manquer dans une copie et le kwarg mourir sur ce composant seul.
    """
    assert "*:basis-64" in classes(lambda: cls(grow="16rem"))
