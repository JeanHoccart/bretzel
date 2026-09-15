"""Gate : un ``min=`` mal formé ne fait pas exploser le DOM.

Le défaut qu'elle ferme (2026-08-27)
------------------------------------
Le menu de saut d'année d'un calendrier rend **un ``<button>`` par
année**, en dur dans le DOM, sur l'étendue ``min``..``max``. Sans
plafond, cette étendue venait telle quelle de la valeur reçue — et
``int("137".split("-")[0])`` vaut l'an 137 ::

    ui.date_picker(min="2026-01-01")  ->   17 622 o,    29 <button>
    ui.date_picker(min="137")         ->  463 581 o, 1 918 <button>

Le rendu serveur reste instantané (0,01 s), ce qui est exactement ce qui
rend le défaut invisible côté Python : **c'est le navigateur qui paie**,
~114 s pour avaler le résultat. ``pytest -m audit`` pendait dessus, et
c'est comme ça qu'on l'a trouvé — la sonde tape une sentinelle numérique
dans chaque champ texte du playground, et elle est tombée sur ce cas
sans le chercher.

L'invariant
-----------
Un composant qui accepte ``min=`` répond de l'une des deux façons
acceptables à une valeur aberrante :

- il la **refuse** (``number_input`` et ``slider`` lèvent sur une date —
  leur ``min`` est un nombre) ;
- il la **borne** (la famille date plafonne son menu d'années).

Ce qu'aucun ne fait, c'est rendre un DOM proportionnel à l'absurdité de
l'entrée. Le seuil est un RATIO contre le rendu nu du même composant,
pas une taille absolue : les composants font de 631 o à 22 Ko à vide, et
un seuil absolu dirait n'importe quoi de la moitié d'entre eux.

Les deux versants
-----------------
Le versant illicite (« ça n'explose pas ») se satisferait d'un plafond
absurdement bas qui couperait les usages réels. Le versant LICITE le
tient : ``min="1900-01-01"`` — une date de naissance — doit passer
INTACTE, ses 137 années comprises, et le menu doit toujours contenir
l'année affichée. Un plafond qui perdrait l'année qu'on regarde serait
pire que le défaut qu'il répare.
"""

from __future__ import annotations

import re

import pytest

from bretzel.components.base.testing import render_isolated
from bretzel.components.inputs.calendar.calendar import MAX_YEARS_IN_DROPDOWN
from bretzel.core.serialize import serialize
from tests.consistency._discovery import (
    bare_kwargs,
    public_component_classes,
    ui_name_of,
)

#: Preuve de morsure : le versant licite. Un plafond trop serré — la
#: façon la plus facile de « fermer » ce défaut — fait tomber ce test.
MUTATION_PROOF = "test_a_legitimate_wide_range_survives_untouched"

#: Mesuré le 2026-08-27, borne en place : le pire est ``month_picker`` à
#: 3,9×. Sans borne, ``date_picker`` était à **26×**. 6 laisse de la marge
#: à un composant qui grandirait honnêtement, et reste très loin du cas
#: pathologique.
_MAX_RATIO = 6.0

#: Des ``min=`` qu'aucun appelant sensé n'écrit — mais qu'un champ d'état
#: momentanément mal rempli produit tout seul.
_ABSURD = ("137", "42", "0001-01-01")

#: 9 composants le 2026-08-27. Le plancher attrape un
#: ``__reactive_props__`` mal lu — la gate serait verte sans sujet.
_CARRIERS_FLOOR = 8


def _min_max_components() -> list[type]:
    return sorted(
        (
            cls for cls in public_component_classes()
            if {"min", "max"} <= set(getattr(cls, "__reactive_props__", {}))
        ),
        key=lambda c: c.__name__,
    )


def _render(cls: type, **extra) -> str:
    with render_isolated():
        return serialize(cls(**bare_kwargs(cls), **extra).render())


_CARRIERS = _min_max_components()
_IDS = [c.__name__ for c in _CARRIERS]


def test_the_sweep_is_not_vacuous() -> None:
    assert len(_CARRIERS) >= _CARRIERS_FLOOR, (
        f"seulement {len(_CARRIERS)} composants avec ``min`` ET ``max`` "
        f"découverts (9 le 2026-08-27) — vérifie que "
        f"``__reactive_props__`` se lit encore avant de croire que cette "
        f"gate passe."
    )


@pytest.mark.parametrize("cls", _CARRIERS, ids=_IDS)
def test_an_absurd_min_does_not_explode_the_dom(cls: type) -> None:
    base = len(_render(cls))
    for value in _ABSURD:
        try:
            size = len(_render(cls, min=value))
        except Exception:
            # Refuser est une réponse LÉGITIME — c'est celle de
            # ``number_input`` et ``slider``, dont le ``min`` est un
            # nombre. Ce qu'on interdit, c'est de rendre quand même.
            continue
        ratio = size / base
        assert ratio <= _MAX_RATIO, (
            f"``{ui_name_of(cls)}(min={value!r})`` rend {size} octets "
            f"contre {base} à vide — {ratio:.1f}× le rendu nu.\n"
            f"  Une valeur aberrante ne doit pas produire un DOM "
            f"proportionnel à son absurdité : le rendu serveur reste "
            f"instantané, c'est le NAVIGATEUR qui paie (114 s mesurées "
            f"sur 463 Ko).\n"
            f"  Borne la population rendue, ou refuse la valeur — les "
            f"deux réponses sont acceptables, rendre ne l'est pas."
        )


def test_a_legitimate_wide_range_survives_untouched() -> None:
    """Le versant LICITE — et la preuve que le plafond n'est pas bidon.

    Une date de naissance remonte à ~120 ans, et ce menu est le SEUL
    moyen d'y sauter. Un plafond qui couperait ce cas « fermerait » le
    défaut en cassant l'usage — ce qui est la façon la plus facile de
    rendre cette gate verte, donc celle qu'il faut interdire.
    """
    from bretzel import ui

    with render_isolated():
        html = serialize(ui.date_picker(min="1900-01-01").render())
    years = sorted({int(y) for y in re.findall(r">(\d{4})</", html)})
    assert years and years[0] == 1900, (
        f"``min='1900-01-01'`` ne remonte plus qu'à {years[0] if years else '—'} "
        f"— le plafond mord un usage RÉEL (une date de naissance). "
        f"Il est fait pour les valeurs aberrantes, pas pour celle-ci."
    )
    assert len(years) <= MAX_YEARS_IN_DROPDOWN


def test_the_window_always_contains_the_displayed_year() -> None:
    """Un plafond qui perd l'année affichée est pire que le défaut.

    Tronquer l'étendue d'un bout est le raccourci évident, et il donne un
    menu qui ne contient PAS l'année qu'on regarde : ouvrir le calendrier
    sur 1912 et ne pouvoir sauter qu'entre 1837 et 2036 rend le contrôle
    inutile là où il servirait le plus.
    """
    from bretzel import ui

    with render_isolated():
        html = serialize(
            ui.date_picker(min="137", value="1912-04-15").render()
        )
    years = {int(y) for y in re.findall(r">(\d{4})</", html)}
    assert 1912 in years, (
        f"la fenêtre d'années ne contient PAS l'année affichée (1912) : "
        f"{min(years)}..{max(years)}. Le plafond doit être CENTRÉ sur "
        f"l'année affichée, pas tronqué d'un bout."
    )
    assert len(years) <= MAX_YEARS_IN_DROPDOWN
