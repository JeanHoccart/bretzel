"""Les six props de ``ui.flex`` refusent une valeur hors table.

Le defaut qu'elles fermaient a moitie
--------------------------------------
Cinq des six faisaient ``table.get(value, "")`` : ``ui.hstack(align="stretchy")``
rendait une classe **VIDE**, sans erreur, sans warning, avec un HTML
parfaitement valide. C'est le kwarg mort — le mode d'echec dominant de ce
depot, parce qu'il ne leve pas, ne s'affiche pas, et ne se voit pas en
revue.

``grow=`` refusait deja (livre le 2026-08-25), ce qui laissait DEUX
mecanismes pour une meme classe d'erreur dans une seule methode : un
lecteur de ``_compose_classes`` devait savoir laquelle des six levait.
Principe 4 du charter — une seule maniere de faire chaque chose.

Ce que le changement a coute, mesure avant
-------------------------------------------
Balayage AST de ``bretzel/`` + ``examples/`` + ``tests/`` le 2026-08-29 :
**2 366 passages litteraux**, et **2 valeurs hors table** — les deux
``gap="2xs"`` d'``examples/playground/features/dnd.py``, un palier qui n'a
jamais existe dans la table (``none/xs/sm/md/lg/xl``). Deux piles sans
gouttiere depuis le premier jour, que personne n'avait vues. Corrigees
dans le meme commit.

La levee vit dans ``__init__``, pas au rendu : une exception levee depuis
``_compose_classes`` remonte une pile sans aucune frame de l'appelant, donc
elle nomme les valeurs acceptees sans dire lequel des N appels de la page
est fautif. Meme raison, meme place que pour ``grow=``.
"""

from __future__ import annotations

import pytest

from bretzel.components.base.attrs import ComponentUsageError
from bretzel.components.base.testing import render_isolated
from bretzel.components.layout.flex.flex import Flex
from bretzel.components.layout.stack.stack import HStack, VStack

#: Une valeur credible mais absente, par prop. Credible est le point : le
#: kwarg mort ne vient pas d'une faute de frappe grossiere, il vient d'un
#: nom qu'on croit exister.
_HORS_TABLE = {
    "direction": "vertical",
    "align": "stretchy",
    "justify": "space-between",
    "gap": "2xs",
    "grow": "auto",
}

#: Le versant LICITE, prop par prop — sans lui, refuser TOUT passerait
#: aussi bien.
_DANS_TABLE = {
    "direction": "col",
    "align": "center",
    "justify": "between",
    "gap": "lg",
    "grow": "equal",
}


@pytest.mark.parametrize("prop", sorted(_HORS_TABLE))
def test_a_value_off_table_is_refused(prop: str) -> None:
    with render_isolated(), pytest.raises(ComponentUsageError) as leve:
        Flex(**{prop: _HORS_TABLE[prop]})
    message = str(leve.value)
    assert _HORS_TABLE[prop] in message, "le message doit citer la valeur refusee"
    assert _DANS_TABLE[prop] in message, (
        "le message doit ENUMERER les valeurs acceptees — sans ca, "
        "l'auteur ne sait pas quoi ecrire a la place"
    )


@pytest.mark.parametrize("prop", sorted(_DANS_TABLE))
def test_a_value_in_the_table_still_passes(prop: str) -> None:
    with render_isolated():
        Flex(**{prop: _DANS_TABLE[prop]})


@pytest.mark.parametrize("cls", [HStack, VStack], ids=["hstack", "vstack"])
def test_the_shortcuts_refuse_too(cls: type) -> None:
    """``HStack`` / ``VStack`` heritent du refus — ce sont eux qu'on ecrit."""
    with render_isolated(), pytest.raises(ComponentUsageError):
        cls(align="stretchy")


def test_a_breakpoint_dict_is_checked_value_by_value() -> None:
    """Une prop graduee est validee palier par palier.

    La CLE est un nom de point de rupture (``md``), la VALEUR est ce qui
    doit vivre dans la table. Sans cette distinction, soit on refuse tous
    les dicts, soit on n'en valide aucun.
    """
    with render_isolated():
        Flex(gap={"base": "sm", "md": "lg"})          # licite

    with render_isolated(), pytest.raises(ComponentUsageError) as leve:
        Flex(gap={"base": "sm", "md": "2xs"})
    assert "2xs" in str(leve.value)
