"""Gate : ``bretzel/py.typed`` est là, à côté de ``__init__.py``.

PEP 561 : sans ce marqueur, un vérificateur de types considère le paquet
comme non annoté et ignore tout ce qu'il déclare — même quand le code est
entièrement typé et que ``mypy --strict`` passe dans le dépôt. Le paquet
paraît alors non typé de l'extérieur, et rien ne le dit.

On regarde le RÉPERTOIRE DU PAQUET (celui qui porte ``__init__.py``), pas
le dépôt entier : un ``py.typed`` écrit au mauvais endroit satisfait un
balayage large et ne satisfert aucun vérificateur.
"""

from __future__ import annotations

import pathlib

import bretzel

MUTATION_NOT_APPLICABLE = (
    "no detector: the test asserts the file itself — if the marker "
    "disappears, the assertion is what fails"
)


def test_the_package_carries_its_py_typed_marker() -> None:
    """Le marqueur vit dans le répertoire du paquet, pas à côté."""
    racine = pathlib.Path(bretzel.__file__).parent
    marqueur = racine / "py.typed"
    assert marqueur.is_file(), (
        f"{marqueur} est absent.\n"
        f"  Sans lui (PEP 561) les vérificateurs ignorent les annotations "
        f"de {racine.name}/ pour un consommateur qui l'installe."
    )
