"""Tout opérateur de l'algèbre rend une ``ClientExpression`` ATOMIQUE.

Atomique = interpolable dans une expression plus large **sans re-associer**.
C'est la propriété qui rend l'algèbre de bindings composable : chaque
opérateur reçoit des opérandes dont il n'a pas à connaître la forme
interne.

⚠️ **Périmètre : les opérateurs.** ``ClientExpression("…")`` construite à la
main accepte n'importe quelle source — `meta/iteration/{filter,limit,
paginate}_each` en bâtissent quatre non-atomiques. Elles servent de valeur
TERMINALE à ``visible=`` (un ``bz-show`` entier, jamais un opérande), donc
rien ne casse ; normaliser dans ``__init__`` fermerait le trou pour de bon
mais mettrait un scan de chaîne sur le chemin de rendu — arbitrage
consigné dans `todo.md`, pas tranché ici.

Le bug qui a motivé cette gate (audit A2-bis, 2026-07-15 ; corrigé
2026-07-28) : les comparaisons ne parenthésaient pas leur résultat, donc
``~(state.n > 0)`` sortait ``!$bz.state.S.default.n > 0``. JS lit ça
``(!$n) > 0``. Prouvé sous node avec ``n = -1`` : attendu ``true``, réel
``false``. **Divergence silencieuse, résultat faux** — aucune erreur, aucun
log, juste une UI qui ment.

Deux façons d'être atomique :

- **parenthésé** — obligatoire pour tout opérateur *lâche* (``&&``, ``||``,
  ``===``, ``+``, ternaire) ; sans ça l'opérateur hôte se réassocie ;
- **accès membre / appel** — ``$x.length``, ``Math.abs($x)``,
  ``Number($x).toFixed(2)`` : la production JS la plus liante, rien à
  ajouter.

La gate est **auto-évolutive** : `test_producer_registry_is_complete`
échoue si une méthode annotée ``-> ClientExpression`` apparaît sans être
enregistrée dans ``_PRODUCERS``. Un futur opérateur ne peut donc pas
échapper au contrôle en silence — c'était tout le problème, la règle
n'existait nulle part et chaque opérateur la redécidait.
"""

from __future__ import annotations

import re
from collections.abc import Callable

import pytest

from bretzel.state.scopes.client import (
    ClientBinding,
    ClientExpression,
)

# Les caractères qui, rencontrés à la profondeur 0, prouvent que la source
# se re-associe contre son hôte. ``.`` et ``,`` n'en sont pas : l'accès
# membre lie plus fort que tout opérateur, et une virgule ne peut être à
# la profondeur 0 (elle vit dans une liste d'arguments donc entre parens).
_LOOSE_CHARS: str = "+-*/%<>=!&|?:"


def _binding(field_name: str = "n", value: object = 0) -> ClientBinding:
    return ClientBinding(
        class_name="S",
        instance_key="default",
        field_name=field_name,
        value=value,
    )


# Un littéral chaîne peut contenir n'importe quoi — un ``+``, une
# parenthèse déséquilibrée (``empty="(none)"``). On le neutralise AVANT
# de compter, sinon ``$x === "a+b"`` serait lu comme un opérateur
# structurel et la gate crierait à tort.
#
# Guillemets DOUBLES seulement : les producteurs passent tous par
# ``json.dumps``, qui n'émet que ceux-là. Ailleurs le repo écrit du JS en
# guillemets simples (``'true'``) — un futur producteur qui ferait pareil
# ferait crier la gate à tort, et c'est ici qu'il faudrait l'apprendre.
_STRING = re.compile(r'"(?:[^"\\]|\\.)*"')


def top_level_operator(src: str) -> str | None:
    """Le premier opérateur JS à la profondeur 0, ou ``None`` si atomique."""
    depth = 0
    for ch in _STRING.sub('""', src):
        if ch in "([":
            depth += 1
        elif ch in ")]":
            depth -= 1
        elif depth == 0 and ch in _LOOSE_CHARS:
            return ch
    return None


# ── Le registre des producteurs ──────────────────────────────────────
#
# Un builder par méthode qui rend une ``ClientExpression``. Explicite
# (et non introspecté-puis-appelé) parce que chaque opérateur a sa propre
# arité ; la complétude, elle, EST introspectée — cf. le second test.

_PRODUCERS: dict[str, Callable[[], ClientExpression]] = {
    # comparaisons
    "__eq__": lambda: _binding() == 5,
    "__ne__": lambda: _binding() != 5,
    "__lt__": lambda: _binding() < 5,
    "__le__": lambda: _binding() <= 5,
    "__gt__": lambda: _binding() > 5,
    "__ge__": lambda: _binding() >= 5,
    "eq": lambda: _binding().eq(5),
    "ne": lambda: _binding().ne(5),
    "lt": lambda: _binding().lt(5),
    "le": lambda: _binding().le(5),
    "gt": lambda: _binding().gt(5),
    "ge": lambda: _binding().ge(5),
    # arithmétique
    "__add__": lambda: _binding() + 1,
    "__radd__": lambda: 1 + _binding(),
    "__sub__": lambda: _binding() - 1,
    "__rsub__": lambda: 1 - _binding(),
    "__mul__": lambda: _binding() * 2,
    "__rmul__": lambda: 2 * _binding(),
    "__truediv__": lambda: _binding() / 2,
    "__floordiv__": lambda: _binding() // 2,
    "__mod__": lambda: _binding() % 3,
    "__neg__": lambda: -_binding(),
    "__abs__": lambda: abs(_binding()),
    "__round__": lambda: round(_binding(), 2),
    # logique
    "__invert__": lambda: ~_binding(),
    "__and__": lambda: _binding() & _binding("m"),
    "__or__": lambda: _binding() | True,
    "not_": lambda: _binding().not_(),
    # accesseurs nommés
    "between": lambda: _binding().between(0, 100),
    "length": lambda: _binding("items", []).length(),
    "contains": lambda: _binding("tags", []).contains("foo"),
    "then_else": lambda: _binding().then_else("yes", "no"),
    "to_fixed": lambda: _binding().to_fixed(2),
    "join": lambda: _binding("items", []).join(", ", empty="(none)"),
}


@pytest.mark.parametrize("name", sorted(_PRODUCERS))
def test_operator_result_is_atomic(name: str) -> None:
    """Chaque opérateur rend une source interpolable telle quelle."""
    src = _PRODUCERS[name]().binding_path()
    offender = top_level_operator(src)
    assert offender is None, (
        f"ClientBinding.{name} rend une source NON atomique :\n"
        f"    {src}\n"
        f"  L'opérateur {offender!r} est à la profondeur 0, donc "
        f"l'expression se re-associe une fois interpolée dans une plus "
        f"grande — ``~(n > 0)`` a donné ``!$n > 0`` (lu ``(!$n) > 0``, "
        f"résultat FAUX) exactement comme ça.\n"
        f"  Fix : parenthéser le résultat, comme le font déjà "
        f"``__add__`` / ``__and__`` / ``then_else``."
    )


def test_member_access_on_an_expression_stays_atomic() -> None:
    """Chaîner un accès membre sur une comparaison.

    Le pendant du cas ``~(n > 0)`` (couvert côté unitaire par
    ``test_invert_of_a_comparison_negates_the_comparison``) : ici c'est le
    ``.length`` qui mordrait le dernier opérande au lieu du tout.
    """
    chained = (_binding() > 0).length()
    assert chained.binding_path() == "($bz.state.S.default.n > 0).length"


def test_producer_registry_is_complete() -> None:
    """Aucun opérateur n'échappe à la gate.

    Introspecte ``ClientBinding`` : toute méthode annotée
    ``-> ClientExpression`` doit être enregistrée. Sans ça, un opérateur
    ajouté demain hériterait du défaut d'origine (« je ne parenthèse
    pas ») sans que rien ne le signale.
    """
    # ``ClientExpression`` AUSSI : c'est un endroit naturel pour du sucre
    # propre aux expressions, et un opérateur posé là échapperait sinon à
    # la fois à la complétude et à l'atomicité.
    declared = {
        name
        for owner in (ClientBinding, ClientExpression)
        for name, member in vars(owner).items()
        if callable(member)
        and getattr(member, "__annotations__", {}).get("return")
        == "ClientExpression"
    }
    missing = declared - set(_PRODUCERS)
    assert not missing, (
        f"Opérateurs rendant une ClientExpression sans entrée dans "
        f"`_PRODUCERS` : {sorted(missing)}.\n"
        f"  Ajoute un builder pour chacun — la gate d'atomicité ne peut "
        f"pas vérifier ce qu'elle ne construit pas."
    )

    stale = set(_PRODUCERS) - declared
    assert not stale, (
        f"`_PRODUCERS` liste des méthodes qui n'existent plus ou ne "
        f"rendent plus une ClientExpression : {sorted(stale)}."
    )


def test_the_sweep_is_not_vacuous() -> None:
    """Plancher : le registre d'opérateurs n'est pas vide.

    ``test_producer_registry_is_complete`` affirme « aucun opérateur
    n'échappe » ; sur un registre vide, c'est vrai et sans contenu.
    """
    assert len(_PRODUCERS) >= 25, (
        f"seulement {len(_PRODUCERS)} producteurs enregistrés (34 le "
        f"2026-08-19) — le registre a fondu, la complétude ne dit plus rien."
    )


def test_the_detector_still_bites() -> None:
    """Mutation : une chaîne JS est encore reconnue dans une expression.

    Le découpage sur les opérateurs de PREMIER niveau doit ignorer ce
    qui vit dans une chaîne — sinon un ``" ? "`` littéral serait pris
    pour un ternaire et l'expression serait mal parenthésée.
    """
    assert _STRING.search('a + " ? " + b').group(0) == '" ? "'
    assert not _STRING.search("a + b"), "faux positif"
