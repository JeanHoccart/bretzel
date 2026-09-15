"""Aucun sélecteur d'attribut du CSS framework ne vise un attribut mort.

Pourquoi cette gate existe (mesuré au navigateur le 2026-08-19)
---------------------------------------------------------------
``theme/css.py`` porte les quelques règles que Tailwind ne sait pas
exprimer — dont ``_RAIL_SCROLL``, qui masque la barre de défilement du
rail replié. Elle visait ``aside[data-variant="rail"]``.

La Sidebar n'émet plus ``data-variant`` : elle émet ``data-collapse``, et
``sidebar.py`` le dit en toutes lettres (« ``data-collapse`` remplace
``data-variant`` »). La règle ne matchait donc **plus rien**, et le rail
replié rendait sa barre de défilement — mesuré :
``scrollbar-width: thin`` au lieu de ``none``.

**Rien ne lève quand un sélecteur CSS cesse de matcher.** Pas d'erreur,
pas de warning, pas de différence dans le HTML : juste une règle morte et
un défaut visuel que seul un œil (ou un probe) attrape. C'est la
définition de ce que ce dépôt gate.

Ce que la gate affirme, et ce qu'elle n'affirme pas
---------------------------------------------------
Elle affirme que **le NOM d'attribut** de chaque sélecteur est émis par
au moins un composant public — statiquement, ou via un ``bz-attr:`` que
le runtime résoudra.

Elle n'affirme **pas** que la VALEUR est atteignable, et c'est une
abstention mesurée : sur les quatre sélecteurs du jour,
``[aria-disabled="true"]`` n'existe jamais en dur — le composant émet
``bz-attr:aria-disabled="(disabled) ? 'true' : 'false'"`` et la valeur
n'apparaît qu'à l'exécution. Exiger la paire exacte rendrait la gate
rouge sur du code correct, donc destinée à être débranchée.
"""

from __future__ import annotations

import functools
import re

from bretzel.theme import Theme
from tests.consistency._discovery import (
    public_component_classes,
    rendered_html_of,
    ui_name_of,
)

#: Preuve de morsure : le contrôle vit dans ``test_the_detector_still_bites``.
MUTATION_PROOF = "test_the_detector_still_bites"

_ATTR_SELECTOR = re.compile(r'\[([a-zA-Z][a-zA-Z0-9_-]*)=\"([^\"]*)\"\]')


@functools.lru_cache(maxsize=1)
def css_attribute_selectors() -> tuple[tuple[str, str], ...]:
    """Les couples ``(attribut, valeur)`` visés par le CSS du framework."""
    return tuple(sorted(set(_ATTR_SELECTOR.findall(Theme().generate_css()))))


@functools.lru_cache(maxsize=1)
def _emitted_html() -> str:
    """Le HTML de TOUT le catalogue, concaténé.

    Bâti par ``rendered_html_of`` — le lecteur partagé — donc un composant
    qui exige un contexte est DÉCLARÉ non constructible au lieu de sortir
    du balayage en silence.
    """
    return "\n".join(
        html for cls in public_component_classes()
        if (html := rendered_html_of(cls)) is not None
    )


def emits(attribute: str, html: str) -> bool:
    """Un composant pose-t-il cet attribut — en dur ou via ``bz-attr:`` ?"""
    return f'{attribute}="' in html or f"bz-attr:{attribute}=" in html


def offenders() -> list[str]:
    html = _emitted_html()
    return [
        f'[{name}="{value}"] — aucun composant n\'émet ``{name}``'
        for name, value in css_attribute_selectors()
        if not emits(name, html)
    ]


def test_the_sweep_is_not_vacuous() -> None:
    """Deux planchers : les sélecteurs, et le corpus qui les juge."""
    selectors = css_attribute_selectors()
    assert len(selectors) >= 3, (
        f"seulement {len(selectors)} sélecteur(s) d'attribut trouvé(s) dans "
        f"le CSS (4 le 2026-08-19) — l'extraction est cassée, et « aucun "
        f"sélecteur ne vise un attribut mort » serait affirmé sur rien."
    )
    rendered = sum(
        1 for cls in public_component_classes() if rendered_html_of(cls) is not None
    )
    assert rendered >= 85, (
        f"seulement {rendered} composants rendus (93 le 2026-08-19) — le "
        f"corpus qui décide « personne n'émet cet attribut » est amputé, "
        f"donc il condamnerait des attributs bien vivants."
    )


def test_no_css_selector_targets_a_dead_attribute() -> None:
    found = offenders()
    assert not found, (
        "Le CSS du framework vise des attributs que plus aucun composant "
        "n'émet. Une règle qui ne matche plus ne LÈVE pas : elle disparaît "
        "en silence, et seul un œil voit le défaut. C'est comme ça que le "
        "rail replié a repris sa barre de défilement :\n  "
        + "\n  ".join(found)
    )


def test_the_detector_still_bites() -> None:
    """Les deux versants, sur le renommage RÉEL qui a causé le bug."""
    html = _emitted_html()
    assert not emits("data-variant", html), (
        "``data-variant`` est de nouveau émis par un composant — le cas "
        "historique n'en est plus un, mets à jour cette preuve."
    )
    assert emits("data-collapse", html), (
        "``data-collapse`` n'est plus émis : le détecteur dirait « mort » "
        "de tout, y compris du nom correct."
    )
    # Le versant qui compte vraiment : la forme ``bz-attr:`` doit COMPTER
    # comme une émission, sinon la gate condamnerait tout attribut
    # purement réactif — ``aria-disabled`` le premier.
    assert not emits("aria-disabled", '<div aria-disabledX="true">')
    assert emits("aria-disabled", '<div bz-attr:aria-disabled="x">')


def test_every_selector_names_a_component_that_emits_it() -> None:
    """Le versant utile en revue : QUI émet chaque attribut visé."""
    owners = {
        name: sorted(
            ui_name_of(cls)
            for cls in public_component_classes()
            if (html := rendered_html_of(cls)) is not None and emits(name, html)
        )
        for name, _ in css_attribute_selectors()
    }
    orphans = [name for name, who in owners.items() if not who]
    assert not orphans, f"aucun composant n'émet {orphans} — carte : {owners}"
