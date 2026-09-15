"""Gate : une largeur passée en ``classes=`` doit GAGNER sur celle du thème.

``classes=`` est l'échappatoire unique du framework (« Escape hatch unique :
``classes="..."`` pour les cas atypiques », ``bretzel describe``). Une
échappatoire qui n'échappe pas silencieusement est pire qu'absente : on
écrit la classe, on la voit dans le HTML, et rien ne bouge.

C'est exactement ce qui se passait. ``_append_attr`` concatène la valeur de
l'utilisateur APRÈS celle du thème, et sa docstring en tirait la conclusion
« so a user override wins on source order ». **Faux** : entre deux
utilitaires Tailwind concurrents, c'est l'ordre dans la FEUILLE générée qui
tranche, jamais l'ordre dans l'attribut ``class``. Mesuré le 2026-08-15 sur
``examples/chat`` — ``ui.card(classes="w-fit")`` rendait des bulles de
672 px pour le mot « test », et il fallait ``!w-fit`` pour s'en sortir.

La portée n'était pas anecdotique : **plus de vingt thèmes** bakent une
largeur sur leur slot ``root``. Sur tous, ``classes="w-1/2"`` / ``"w-64"``
/ ``"w-fit"`` étaient sans effet.

Ce que la gate protège, et c'est plus large que ``ui.card`` :

1. une largeur de même portée est RETIRÉE du thème (le conflit se résout
   dans le HTML, où on le maîtrise) ;
2. une largeur d'une AUTRE portée ne l'est pas — ``md:w-1/2`` ne doit pas
   emporter le ``w-full`` de base, sinon le composant perd sa largeur sous
   le breakpoint ;
3. ``max-w-`` / ``min-w-`` ne sont PAS des largeurs — autres propriétés
   CSS, elles composent au lieu de contredire ;
4. le plancher : au moins un composant public bake réellement une largeur,
   sans quoi (1) passerait sur un corpus vide.
"""

from __future__ import annotations

import re

import pytest

from bretzel.components.base.component import _drop_widths, _width_scopes
from bretzel.components.base.testing import render_isolated
from bretzel.core.serialize import serialize
from tests.consistency._discovery import public_component_classes, rendered_html_of

_CLASS_ATTR = re.compile(r'class="([^"]*)"')
_BARE_WIDTH = re.compile(r"(?:^|\s)!?w-\S+")


@pytest.mark.parametrize(
    ("theme", "user", "expected"),
    [
        # (1) même portée → la largeur du thème saute
        ("block w-full rounded-xl", "w-fit", "block rounded-xl"),
        ("flex w-full min-w-0", "w-64", "flex min-w-0"),
        # le ``!`` de l'appelant vaut déclaration : il ne doit plus être requis
        ("block w-full", "!w-fit", "block"),
        # (2) portée DIFFÉRENTE → on ne touche à rien
        ("block w-full rounded-xl", "md:w-1/2", "block w-full rounded-xl"),
        ("block w-full md:w-auto", "md:w-1/2", "block w-full"),
        # (3) max-w / min-w ne sont pas des largeurs
        ("block w-full max-w-lg", "max-w-xl", "block w-full max-w-lg"),
        ("block w-full min-w-0", "min-w-full", "block w-full min-w-0"),
        # aucune largeur déclarée → aucun retrait
        ("block w-full", "rounded-none", "block w-full"),
    ],
)
def test_width_conflict_rules(theme: str, user: str, expected: str) -> None:
    assert _drop_widths(theme, _width_scopes(user)) == expected


def test_a_card_can_size_to_its_content() -> None:
    """Le cas concret qui a révélé le défaut, bout en bout.

    Pas une vérification d'unité sur les helpers : on RÉSOUT le composant
    et on lit la ``class`` qui part sur le fil. Les helpers pourraient être
    parfaits et n'être appelés nulle part — c'était d'ailleurs l'état du
    monde, ``_append_attr`` concaténant sans rien retirer.
    """
    from bretzel import ui

    with render_isolated():
        card = ui.card(classes="w-fit max-w-[42rem]")
        with card:
            ui.text("test")
    html = serialize(card.render())

    classes = _CLASS_ATTR.search(html)
    assert classes, "la carte ne rend aucune classe — le test ne mesure rien"
    rendered = classes.group(1)

    assert "w-fit" in rendered, f"le w-fit de l'appelant a disparu : {rendered!r}"
    assert "w-full" not in rendered, (
        f"le w-full du thème survit à un w-fit explicite : {rendered!r}.\n\n"
        "L'ordre dans l'attribut class ne tranche PAS entre deux utilitaires "
        "Tailwind — c'est l'ordre dans la feuille générée. Il faut donc "
        "retirer la largeur du thème (_append_attr), pas se fier à la "
        "concaténation."
    )
    assert "max-w-[42rem]" in rendered, (
        f"max-w a été emporté avec w-full : {rendered!r}. C'est une autre "
        "propriété CSS, elle compose avec width."
    )


def test_at_least_one_public_component_bakes_a_width() -> None:
    """Plancher — il porte sur la DÉCOUVERTE, pas sur une population.

    Le test du dessus vérifie qu'un ``w-full`` de thème saute. Il passerait
    tout aussi bien si plus AUCUN thème n'en posait — auquel cas la règle
    ne protégerait plus rien et personne ne l'apprendrait. On exige donc
    qu'un composant public en bake encore une, en la lisant sur le rendu
    et non dans les sources (c'est la classe émise qui compte).

    Le seuil est à 1 et non au nombre mesuré (~20) : ce plancher garde la
    PERTINENCE de la règle, pas l'inventaire des thèmes, qui a le droit de
    bouger sans faire rougir une gate de composition.
    """
    bakers: list[str] = []
    for cls in public_component_classes():
        html = rendered_html_of(cls)
        if html is None:
            continue
        found = _CLASS_ATTR.search(html)
        if found and _BARE_WIDTH.search(found.group(1)):
            bakers.append(cls.__name__)

    assert bakers, (
        "Aucun composant public ne bake plus de largeur sur sa racine — la "
        "règle du retrait ne protège donc plus rien, et le test qui la "
        "vérifie passe sur un cas fabriqué. Vérifier que le balayage "
        "construit bien des composants avant de conclure que la dérive a "
        "disparu."
    )


def test_the_detector_still_bites() -> None:
    """Mutation : une largeur BAKÉE sur la racine est encore reconnue.

    Les deux regex se relaient — l'une extrait le ``class=``, l'autre y
    cherche un jeton de largeur nu. Si l'une des deux cessait de
    matcher, la règle du retrait ne protégerait plus rien tout en
    restant verte.
    """
    found = _CLASS_ATTR.search('<div class="w-full rounded-md">')
    assert found, "l'extraction du ``class=`` ne matche plus"
    assert _BARE_WIDTH.search(found.group(1)), "``w-full`` devrait mordre"
    assert _BARE_WIDTH.search("rounded !w-64"), "une largeur ``!`` devrait mordre"
    for licit in ("rounded-md p-4", "max-w-full", "sm:w-64"):
        assert not _BARE_WIDTH.search(licit), f"{licit!r} : faux positif"
