"""Aucun contrôle n'est caché derrière un survol.

Un doigt ne survole pas. Un élément posé à ``opacity-0`` qui compte sur
``group-hover:opacity-100`` pour se montrer n'apparaît, au toucher, qu'au
prix d'un premier tap — donc jamais pour qui ne sait pas qu'il y a quelque
chose à révéler.

Historique du diagnostic : le premier symptôme venait de ce que Tailwind v4
enveloppe chaque variante ``hover:`` dans ``@media (hover: hover)``, et que
la condition est **fausse** sur un portable Windows à écran tactile — la
règle n'existait alors pas du tout. Ce point-là est corrigé au niveau du
thème (``@custom-variant hover``, cf.
``test_v4_dropped_defaults_are_restored``), mais il ne change rien à cette gate :
la règle existe désormais, le geste qui la déclenche manque toujours.

Quand l'élément caché porte une action, ce n'est pas un défaut cosmétique :
la fonction devient **inatteignable**. Le cas qui a motivé cette gate est
la croix de suppression de ``file_upload`` — le seul moyen de retirer un
fichier. Reproduit au navigateur : ``has_touch=True`` → ``opacity: 0`` au
survol, contre ``1`` à la souris.

Le symptôme est trompeur, parce que ``focus-visible`` continue de marcher :
au clavier la croix apparaît, ce qui donne l'illusion d'un CSS sain.

**La règle retenue est la plus simple : on affiche le contrôle en
permanence.** On aurait pu compenser avec ``[@media(hover:none)]``, mais
ça revient à maintenir deux chemins pour la même affordance. Un contrôle
ne se cache pas derrière un geste que l'appareil ne sait pas produire ;
``hover:`` reste bienvenu pour ENRICHIR (teinte, ombre), jamais pour
révéler. Le retour au toucher se porte en ``active:``, qui marche partout.

**Baseline vide** — la dette est intégralement payée (le seul cas du
catalogue, ``file_upload.remove_btn``, est corrigé). La gate n'a donc rien
à tolérer : toute nouvelle occurrence est une régression.
"""

from __future__ import annotations

import re

import pytest

from tests.consistency._discovery import (
    ParsedSource,
    theme_slot_strings,
    theme_sources,
)

_THEMES = theme_sources()

# La révélation au survol : ``group-hover:opacity-100`` / ``hover:opacity-100``
# (avec ou sans nom de groupe : ``group-hover/rail:``).
_REVEAL = re.compile(r"\b(?:group-)?hover(?:/[\w-]+)?:opacity-(?:100|\d+)\b")


@pytest.mark.parametrize("theme", _THEMES, ids=lambda s: s.path.parent.name)
def test_no_slot_is_revealed_only_on_hover(theme: ParsedSource) -> None:
    source = theme.text
    offenders = [
        slot
        for slot, classes in theme_slot_strings(source)
        if "opacity-0" in classes.split() and _REVEAL.search(classes)
    ]
    assert not offenders, (
        f"{theme.path.parent.name} : slot(s) {offenders} posés à "
        f"``opacity-0`` puis révélés au SURVOL.\n"
        f"  Un doigt ne survole pas : au toucher l'élément ne se montre "
        f"qu'au prix d'un premier tap, donc jamais pour qui ignore qu'il y a "
        f"quelque chose à révéler — et s'il porte une action, elle devient "
        f"inatteignable.\n"
        f"  Trompeur : ``focus-visible`` continue de marcher, donc au "
        f"clavier tout a l'air normal.\n"
        f"  Fix : affiche-le en permanence (retire ``opacity-0`` et la "
        f"révélation). ``hover:`` enrichit, il ne révèle pas ; le retour au "
        f"toucher se porte en ``active:``."
    )


def test_the_sweep_is_not_vacuous() -> None:
    """Plancher : les thèmes balayés existent encore.

    L'interdiction « aucun slot n'est révélé au seul survol » passe tout
    aussi bien sur zéro thème — et le Chrome de l'utilisateur n'a AUCUN
    pointeur fin, donc ce qui est gaté sur le survol y est mort.
    """
    assert len(_THEMES) >= 60, (
        f"seulement {len(_THEMES)} thèmes de composant balayés (72 le "
        f"2026-08-19) — le glob est cassé."
    )


def test_the_detector_still_bites() -> None:
    """Mutation : la révélation au survol est encore reconnue.

    L'interdiction ci-dessus passerait sur zéro thème si la regex
    cessait de matcher — et le Chrome de l'utilisateur n'a AUCUN
    pointeur fin, donc ce qui est gaté sur le survol y est mort.
    """
    for offending in (
        "opacity-0 group-hover:opacity-100",
        "opacity-0 hover:opacity-100",
        "opacity-0 group-hover/item:opacity-100",
    ):
        assert _REVEAL.search(offending), f"{offending!r} devrait mordre"
    for licit in (
        "opacity-0 focus-visible:opacity-100",
        "opacity-0 group-data-[open=true]:opacity-100",
        "hover:bg-primary",
    ):
        assert not _REVEAL.search(licit), f"{licit!r} : faux positif"
