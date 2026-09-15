"""Gate : ``bretzel describe <nom>`` rend une fiche pour CHAQUE symbole.

Le trou qu'elle ferme, et il était béant
----------------------------------------

``describe`` est la porte que le charter met en avant — « avant d'écrire un
appel ``ui.*``, demande, ne devine pas ». Or rien n'appelait
:func:`~bretzel.introspect.emit.text.render_detail` sur l'ensemble du
catalogue : la découverte des noms était couverte, mais la fiche détaillée ne
l'était par rien.

Résultat, mesuré le 2026-08-16 : ``bretzel describe heading`` **levait un
``TypeError``**, livré tel quel au commit ``c278161a``. Cause :
``Heading.THEME["level_sizes"]`` est indexé par les entiers ``1..6``
(``level=`` est un int, pas une chaîne), et l'émetteur faisait un
``", ".join`` sur des clés supposées ``str``. Un seul composant sur 104,
donc invisible à toute vérification ponctuelle — et personne n'écrit un
test pour la commande qui sert à écrire les tests.

Pourquoi rendre plutôt qu'inspecter
------------------------------------

Un test qui vérifierait « ``ComponentInfo.theme`` ne contient que des
chaînes » couvrirait CE bug et rien d'autre. Rendre la fiche exerce la
chaîne entière — description, formatage, alignement, jointures — donc il
attrape aussi la prochaine hypothèse implicite, quelle qu'elle soit. C'est
la différence entre gater une cause et gater un résultat.

Non-vacuité : le nombre de symboles est vérifié, sinon une découverte
cassée rendrait ce fichier vert sur zéro fiche.
"""

from __future__ import annotations

import pytest

from bretzel.introspect import describe_ui_symbol, ui_symbol_names
from bretzel.introspect.emit.text import render_detail

#: Pas de détecteur à rendre aveugle — cf.
#: ``test_a_prohibition_gate_is_mutation_tested``.
MUTATION_NOT_APPLICABLE = (
    "appelle `render_detail` sur chaque symbole et vérifie que ça rend : l'exécution EST le test, il n'y a pas de motif à reconnaître"
)

_NAMES = sorted(ui_symbol_names())


def test_the_catalogue_is_not_empty() -> None:
    """Plancher : la découverte a vraiment trouvé le catalogue."""
    assert len(_NAMES) > 90, (
        f"seulement {len(_NAMES)} symboles `ui.*` découverts — "
        f"`ui_symbol_names()` s'est vidé, et les fiches ci-dessous ne "
        f"vérifient plus grand-chose."
    )


@pytest.mark.parametrize("name", _NAMES)
def test_describe_renders(name: str) -> None:
    """La fiche se rend, et elle n'est pas vide.

    Le contenu n'est pas jugé ici — d'autres gates s'en chargent. Ce qui
    est jugé, c'est qu'aucun symbole ne fasse LEVER la commande.
    """
    body = render_detail(describe_ui_symbol(name))

    assert body.strip(), f"`describe {name}` rend une fiche vide."
    assert f"ui.{name}" in body, (
        f"`describe {name}` ne se nomme pas — la fiche rendue est celle "
        f"d'un autre symbole."
    )
