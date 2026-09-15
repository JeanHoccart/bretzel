"""Gate : une classe de composant a UNE fiche, et c'est celle d'``ui.<nom>``.

Le défaut qu'elle ferme
-----------------------
``bretzel.components`` exporte 115 noms. Cent-deux sont des classes de
composant — ``Button``, ``AccordionItem``, ``DatePicker`` — dont la
fiche existe déjà, riche : params, bindable, events, slots, impératif.
Les treize autres ne sont **pas** du catalogue : des objets-valeur qu'on
nomme dans une signature (``Series``, ``Move``, ``GraphNode``), une
constante, deux fonctions.

Le module était exempté de classement EN ENTIER, avec une raison écrite
qui ne valait que pour la première moitié. Résultat mesuré le
2026-09-06 : ``describe Series`` répondait « n'est ni dans les
composants ni les modules » sur un nom qu'on écrit dans une annotation.

Depuis, ``describe_module`` filtre — et un filtre a exactement deux
façons de mentir, que cette gate prend chacune par un bout :

- **il en retire trop** : un objet-valeur disparaît de la surface
  décrite, comme avant, mais en silence ;
- **il n'en retire pas assez** : une classe de composant devient AUSSI
  un symbole de module, et le lecteur reçoit deux fiches pour un objet —
  dont une plus pauvre, sous un nom qu'il peut taper.

⚠️ La correspondance classe → ``ui.<nom>`` se lit par IDENTITÉ. Une
version par orthographe (``cls.__name__.lower()``) ratait 37 noms sur
48 : elle reconnaissait ``Button`` → ``button`` et manquait tout ce qui
porte un underscore. C'est pourquoi la preuve de morsure porte sur un
nom COMPOSÉ — sur ``Button`` seul, la version cassée passait.
"""

from __future__ import annotations

import importlib

from bretzel.introspect.components import ui_name_of_class
from bretzel.introspect.modules import SECTIONS, _catalogue_names, describe_module


def catalogue_classes_listed_as_module_symbols() -> list[str]:
    """Les classes de composant qu'une section décrirait une SECONDE fois."""
    carte = ui_name_of_class()
    return sorted(
        f"{module}.{symbol.name}"
        for module in SECTIONS
        for symbol in describe_module(module).symbols
        for value in [getattr(importlib.import_module(module), symbol.name, None)]
        if isinstance(value, type) and value in carte
    )


def non_catalogue_exports_missing_from_their_section() -> list[str]:
    """Ce que le filtre a emporté avec le catalogue sans en être."""
    listed = {s.name for s in describe_module("bretzel.components").symbols}
    module = importlib.import_module("bretzel.components")
    filtered = _catalogue_names("bretzel.components")
    return sorted(
        symbol
        for symbol in module.__all__
        if symbol not in filtered and symbol not in listed
    )


def test_the_filter_recognises_the_real_catalogue() -> None:
    """Plancher, sur la découverte de CETTE gate — et contrôle POSITIF.

    Le filtre doit reconnaître une centaine de classes. Zéro se lirait
    comme « rien à filtrer », ce qui est le vert le plus trompeur ici :
    c'est exactement ce que rendrait une carte cassée."""
    assert len(_catalogue_names("bretzel.components")) >= 90, (
        f"le filtre ne reconnaît plus que "
        f"{len(_catalogue_names('bretzel.components'))} classes de "
        f"composant — la carte classe → `ui.<nom>` est cassée, et tout le "
        f"catalogue va se dédoubler en symboles de module."
    )


def test_no_component_class_is_described_twice() -> None:
    assert not catalogue_classes_listed_as_module_symbols(), (
        f"{catalogue_classes_listed_as_module_symbols()} auraient DEUX "
        f"fiches : celle d'`ui.<nom>` et une fiche de symbole, plus "
        f"pauvre, sous un nom qu'on peut taper."
    )


def test_no_value_object_is_swallowed_with_the_catalogue() -> None:
    assert not non_catalogue_exports_missing_from_their_section(), (
        f"{non_catalogue_exports_missing_from_their_section()} sont "
        f"exportés, ne sont pas du catalogue, et ne sont décrits nulle "
        f"part. C'est le défaut d'origine, revenu par le filtre."
    )


def test_the_filter_catches_a_compound_name_and_spares_a_value_object() -> None:
    """La mutation, dans les deux sens.

    Le versant qui MORD porte sur ``AccordionItem`` et pas sur
    ``Button`` : le nom d'un seul mot passe même avec une carte réduite
    aux orthographes identiques, donc il ne prouve rien.
    """
    filtered = _catalogue_names("bretzel.components")
    assert "AccordionItem" in filtered
    assert "Button" in filtered
    assert "Series" not in filtered
    assert "apply_query" not in filtered
