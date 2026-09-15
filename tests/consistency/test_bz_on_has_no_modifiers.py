"""Gate : ``bz-on:`` n'accepte AUCUN modificateur — le runtime prend le
suffixe verbatim comme nom d'événement.

Ce que ça casse
---------------
``02_directives.js:274`` fait ``name.slice(6)`` et passe le résultat tel
quel à ``addEventListener``. Donc ``bz-on:scroll.passive`` enregistre un
écouteur sur un événement **littéralement nommé** ``"scroll.passive"``,
qui n'existe pas et ne fire jamais. Rien ne lève, rien ne warn, aucun
test SSR ne bronche : le HTML contient bien l'attribut, il est simplement
mort.

Mesuré en livrant le Carousel (2026-08-02). Son pont position→état
passait par ``bz-on:scroll.passive`` : la piste défilait parfaitement,
et l'index ne bougeait jamais. La conséquence en cascade était pire que
le symptôme — ``next()`` lisant un état figé à 0, chaque clic sur la
flèche « suivant » ramenait à la slide 1.

Pourquoi la faute est FACILE
----------------------------
Alpine, Vue et Svelte ont tous des modificateurs d'événement
(``.passive``, ``.stop``, ``.prevent``, ``.window``, ``.once``,
``.self``, ``.debounce``). L'API ``bz-on:`` en a la syntaxe exacte SANS
en avoir la sémantique, et le dépôt vient d'Alpine — c'est de la mémoire
musculaire qui coûte un handler mort. Le remplacement de ``.window``
existe déjà (``$bz.helpers.onWindow``, ``06_helpers.js``), ce qui prouve
que le besoin est réel et que la voie est un helper, pas un suffixe.

Ce qu'on perd en retirant ``.passive`` : rien d'observable. Un écouteur
``scroll`` n'est de toute façon pas annulable ; pour ``wheel`` /
``touchstart`` le drapeau n'est qu'un indice de performance, et nos
handlers n'appellent jamais ``preventDefault``.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

from tests.consistency._discovery import parsed_sources

_COMPONENTS = Path(__file__).resolve().parents[2] / "bretzel" / "components"

#: 272 fichiers sous ``bretzel/components`` le 2026-08-19 ; le plancher
#: laisse de la marge pour une réorganisation sans laisser passer un
#: balayage mort.
_COMPONENTS_FLOOR = 200

#: Un nom d'attribut ``bz-on:`` dont l'événement porte un point.
#: ``bz-on:htmx:after-request`` reste licite (deux-points, pas un point) —
#: c'est un vrai nom d'événement htmx.
_MODIFIED = re.compile(r"^bz-on:[A-Za-z0-9_:-]+\.")

#: Plancher de non-vacuité : sous ce nombre de littéraux ``bz-on:``
#: trouvés, c'est la DÉCOUVERTE qui est cassée (chemin déplacé, forme
#: d'attribut changée), pas le dépôt qui serait devenu propre. Mesuré à
#: 96 le 2026-08-02 ; le plancher est volontairement bas pour ne pas
#: rougir sur une suppression légitime.
_FLOOR = 40


def _bz_on_literals() -> list[tuple[Path, str]]:
    """Tous les littéraux de chaîne ``bz-on:…`` des composants.

    En AST et pas en regex de texte : une mention dans un COMMENTAIRE
    (« l'ancien ``bz-on:click.stop`` ») ne doit pas déclencher la gate.
    C'est la faiblesse mesurée sur ``test_playground_demos_the_api``, qui
    lit le source brut et se laisse satisfaire par de la prose.
    """
    found: list[tuple[Path, str]] = []
    for source in parsed_sources(_COMPONENTS, floor=_COMPONENTS_FLOOR):
        path = source.path
        for node in ast.walk(source.tree):
            if (
                isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and node.value.startswith("bz-on:")
            ):
                found.append((path, node.value))
    return found


_LITERALS = _bz_on_literals()


def test_the_sweep_is_not_vacuous() -> None:
    """La découverte trouve-t-elle encore quelque chose ?"""
    assert len(_LITERALS) >= _FLOOR, (
        f"{len(_LITERALS)} littéraux ``bz-on:`` trouvés sous "
        f"{_COMPONENTS} — plancher {_FLOOR}.\n"
        f"  Un balayage vide passe l'interdiction ci-dessous EXACTEMENT "
        f"comme un dépôt propre. Si les composants ont déménagé ou si la "
        f"forme d'attribut a changé, c'est CETTE fonction qu'il faut "
        f"réparer, pas le plancher qu'il faut baisser."
    )


def test_no_component_uses_an_event_modifier() -> None:
    """``bz-on:<event>.<modifier>`` = un écouteur mort, en silence."""
    offenders = [
        f"{path.relative_to(_COMPONENTS)} : {literal!r}"
        for path, literal in _LITERALS
        if _MODIFIED.match(literal)
    ]
    assert not offenders, (
        "Ces attributs portent un modificateur d'événement, que le "
        "runtime ne connaît pas :\n  " + "\n  ".join(offenders) + "\n\n"
        "  ``02_directives.js`` passe le suffixe VERBATIM à "
        "``addEventListener`` : ``bz-on:scroll.passive`` écoute un "
        "événement nommé « scroll.passive », qui ne fire jamais. Rien ne "
        "lève, le HTML contient bien l'attribut, et le handler est mort.\n"
        "  Retire le modificateur. S'il portait vraiment un besoin "
        "(écouter sur window, débouncer), la voie est un helper runtime — "
        "cf. ``$bz.helpers.onWindow``, qui existe pour exactement ça."
    )


@pytest.mark.parametrize(
    "sample",
    ["bz-on:scroll.passive", "bz-on:click.stop", "bz-on:keydown.enter",
     "bz-on:resize.window", "bz-on:input.debounce"],
)
def test_the_pattern_catches_the_real_shapes(sample: str) -> None:
    """Mutation-test intégré : la regex mord-elle sur les formes que la
    mémoire musculaire Alpine produit vraiment ?"""
    assert _MODIFIED.match(sample), f"{sample} devrait être refusé"


@pytest.mark.parametrize(
    "sample",
    ["bz-on:click", "bz-on:change", "bz-on:bz-set", "bz-on:htmx:after-request",
     "bz-on:pointerdown", "bz-on:bz-expand-all"],
)
def test_the_pattern_spares_the_legitimate_shapes(sample: str) -> None:
    """L'autre sens : un tiret, un deux-points ou un préfixe ``bz-``
    ne sont PAS des modificateurs. Sans ce versant, une regex trop
    gourmande interdirait ``bz-on:htmx:after-request``."""
    assert not _MODIFIED.match(sample), f"{sample} devrait être accepté"
