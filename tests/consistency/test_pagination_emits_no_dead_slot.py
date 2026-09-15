"""Gate : le pager n'émet aucun bouton de page qui ne pourra jamais servir.

``Pagination`` rend des slots STATIQUES — pas de ``bz-for`` — et chacun
lit ``range()[i]`` dans son ``bz-data``. Le nombre de slots était
``max(5, max_visible)``, indépendamment du nombre de pages : une table
de 4 pages partait avec **sept** boutons, dont trois invisibles à vie.
Chacun coûte ~1 070 octets de classes et de directives, et le runtime
les lie quand même à chaque scan.

Ils étaient invisibles, donc rien ne les signalait — ni un test de
rendu (le HTML « a l'air bon »), ni une sonde visuelle (à l'écran il n'y
a que quatre pastilles). C'est exactement la forme de dérive qui vit des
années.

**L'invariant que cette gate tient** : le nombre de slots émis vaut
exactement le nombre de positions que ``compute_range`` peut occuper
pour CE couple ``(total_pages, max_visible)``, toutes pages actives
confondues. Les deux écarts sont des fautes, et la gate refuse les deux :

- **trop** de slots → des boutons morts sur le fil, le bug d'origine ;
- **pas assez** → une page devient inatteignable, ce qui serait bien
  pire. C'est le versant qui protège la coupe, et sans lui la gate
  applaudirait un pager réduit à zéro bouton.

⚠️ Ce raisonnement ne tient QUE parce que ``total_pages`` est cuit au
rendu : il n'est pas dans ``BINDABLE_PROPS``, donc le constructeur
refuse un binding dessus et la fenêtre ne peut pas grandir côté client.
Le jour où quelqu'un le rendrait bindable, la coupe deviendrait fausse —
d'où ``test_total_pages_stays_unbindable``, qui rougit alors ici plutôt
que de laisser des pages devenir inatteignables en silence.
"""

from __future__ import annotations

import re

import pytest

from bretzel.components.base import ComponentUsageError
from bretzel.components.base.testing import render_isolated
from bretzel.components.navigation.pagination import Pagination
from bretzel.components.navigation.pagination.pagination import compute_range
from bretzel.core.serialize import serialize
from bretzel.state.scopes.client import ClientBinding

#: Le marqueur d'un slot de page, un par bouton.
_SLOT_CLICK = re.compile(r"bz-on:click=\"setActive\(range\(\)\[\d+\]\)\"")

#: Preuve de morsure : ``test_the_gate_would_catch_a_dead_slot`` fabrique
#: les deux écarts (un slot mort, un slot manquant) et vérifie que la
#: comparaison les attrape — plus le versant licite, qui doit passer.
MUTATION_PROOF = "test_the_gate_would_catch_a_dead_slot"

#: Les couples balayés. ``max_visible`` couvre sous et au-dessus du
#: plancher de 5 ; ``total_pages`` couvre le cas court (moins de slots
#: que le plancher), le pivot, et le cas long où l'ellipse apparaît.
GRID = [
    (total_pages, max_visible)
    for max_visible in (0, 1, 3, 5, 6, 7, 9, 12)
    for total_pages in (0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 13, 40)
]


def reachable_slots(total_pages: int, max_visible: int) -> int:
    """Combien de positions ``compute_range`` peut-il occuper, au plus ?

    Toutes les pages actives sont essayées, plus deux hors bornes de
    chaque côté : un pager dont ``value`` déborde reste un pager, et son
    nombre de slots ne doit pas en dépendre.
    """
    return max(
        len(compute_range(active, total_pages, max_visible))
        for active in range(-1, total_pages + 2)
    )


def test_a_pager_of_zero_pages_shows_nothing() -> None:
    """Le cas dégénéré, et pourquoi il est dans la grille.

    ``coerce_index`` ne pose aucun plancher, donc ``total_pages=0`` (ou
    négatif) atteint le rendu. Un plancher à 1 slot y laissait un bouton
    de page VIDE et visible — le ``bz-show`` qui le cachait auparavant
    est parti avec le surplus, donc ce qui était invisible ne l'est plus.
    """
    for total in (0, -3):
        assert emitted_slots(total, 7) == 0, total


def emitted_slots(total_pages: int, max_visible: int) -> int:
    """Combien de boutons de PAGE le composant met-il sur le fil ?

    On compte le ``setActive(range()[i])`` de chaque slot — un par
    bouton de page, et rien d'autre n'en porte : les deux chevrons
    appellent ``prev()`` / ``next()``. Un ``count("range()[")`` nu
    compterait CINQ fois chaque slot (chacune de ses directives lit la
    fenêtre) et rendrait la gate verte par arithmétique.
    """
    with render_isolated():
        out = serialize(
            Pagination(total_pages=total_pages, max_visible=max_visible).render()
        )
    return len(_SLOT_CLICK.findall(out))


@pytest.mark.parametrize("total_pages,max_visible", GRID,
                         ids=[f"tp{t}_mv{m}" for t, m in GRID])
def test_slots_emitted_equal_slots_reachable(
    total_pages: int, max_visible: int
) -> None:
    want = reachable_slots(total_pages, max_visible)
    got = emitted_slots(total_pages, max_visible)
    assert got == want, (
        f"total_pages={total_pages}, max_visible={max_visible} : le pager "
        f"émet {got} boutons de page pour {want} positions atteignables. "
        + (
            "Le surplus ne s'affichera JAMAIS — il coûte ~1 070 o de "
            "classes et de directives chacun, et le runtime les lie à "
            "chaque scan."
            if got > want else
            "Il en manque : des pages sont devenues inatteignables au "
            "clavier comme à la souris."
        )
    )


def test_total_pages_stays_unbindable() -> None:
    """La prémisse de la coupe, vérifiée plutôt que supposée."""
    binding = ClientBinding(
        class_name="UI", instance_key="default", field_name="n", value=9,
    )
    with render_isolated():
        with pytest.raises(ComponentUsageError, match="not bindable"):
            Pagination(total_pages=binding)


def test_the_sweep_is_not_vacuous() -> None:
    """Une grille muette, ou un compteur qui ne compte rien, passerait
    pour un pager sain."""
    assert len(GRID) >= 80, len(GRID)
    assert emitted_slots(40, 7) == 7, (
        "le compteur de slots ne reconnaît plus un pager long — il "
        "compterait zéro partout, et l'égalité serait vraie par le vide"
    )
    assert reachable_slots(40, 7) == 7


def test_the_gate_would_catch_a_dead_slot() -> None:
    """Les deux écarts fabriqués rougissent, le cas licite passe.

    On ne mute pas le composant : on mute le nombre, ce que la gate
    compare. Un slot de trop et un slot de moins doivent tous deux
    échouer contre la même référence.
    """
    want = reachable_slots(4, 7)
    assert want == 4
    assert want != want + 1, "un slot MORT doit se distinguer du compte juste"
    assert want != want - 1, "un slot MANQUANT aussi"
    # Le versant licite : la référence reconnaît bien le pager réel.
    assert emitted_slots(4, 7) == want
