"""Les panneaux ancrés se ressemblent — ombre, décalage, rayon.

Un panneau ancré (select, combobox, les deux date pickers, dropdown,
popover) s'ouvre au même endroit, pour la même raison : au-dessus du
contenu, collé à son déclencheur. Deux champs voisins dans un formulaire
doivent donc ouvrir des panneaux qui se lisent comme **une famille**.

Ce n'est pas une opinion : ``select/theme.py:81`` déclare « Mirror the
slots Combobox carries for the same purpose » et ``:143`` « toute retouche
ici va en paire ». Le code affirme l'invariant.

**Ce que le recensement des affordances a mesuré (2026-07-28)** : combobox
était le SEUL en ``mt-2 shadow-xl`` là où les cinq autres portaient
``shadow-lg`` (et les trois à décalage ``mt-1``). Une dérive invisible
isolément — il faut voir deux panneaux côte à côte pour la remarquer, ce
qu'aucun test ne faisait.

⚠️ **Portée volontairement étroite.** On compare l'ombre, le décalage et le
rayon : trois axes qui n'ont aucune raison de différer entre panneaux de
même rôle. On ne compare PAS les tables ``sizes`` : combobox porte
légitimement un ``input`` et un ``empty`` que select n'a pas (pas de filtre
client → pas d'état « aucun résultat »), et son trigger utilise
``min-h-[2.5rem]`` là où select fige ``h-10`` — même hauteur, exprimée
autrement parce que le trigger du combobox grandit avec ses pills. Une
gate qui exigerait l'égalité stricte crierait sur des différences
structurelles justifiées, et personne ne l'écouterait longtemps.
"""

from __future__ import annotations

import re

import pytest

from bretzel.components.inputs.combobox.theme import COMBOBOX_THEME
from bretzel.components.inputs.date_picker.theme import DATE_PICKER_THEME
from bretzel.components.inputs.date_range_picker.theme import (
    DATE_RANGE_PICKER_THEME,
)
from bretzel.components.inputs.select.theme import SELECT_THEME
from bretzel.components.overlay.dropdown.theme import DROPDOWN_THEME
from bretzel.components.overlay.popover.theme import POPOVER_THEME

# Les panneaux qui s'ancrent sur un déclencheur et flottent au-dessus du
# contenu. Tooltip est volontairement absent : c'est une bulle transitoire,
# pas une surface de contenu — son ``shadow-md`` est un choix assumé.
_PANELS: dict[str, dict] = {
    "select": SELECT_THEME,
    "combobox": COMBOBOX_THEME,
    "date_picker": DATE_PICKER_THEME,
    "date_range_picker": DATE_RANGE_PICKER_THEME,
    "dropdown": DROPDOWN_THEME,
    "popover": POPOVER_THEME,
}

# Un axe -> le motif qui le repère dans la chaîne de classes.
_AXES: dict[str, re.Pattern[str]] = {
    "ombre": re.compile(r"\bshadow-(?:sm|md|lg|xl|2xl|none)\b"),
    # Les FAMILLES depuis le 2026-08-30, plus les deux sorties. Le motif
    # cherchait les crans d'échelle, qu'aucun thème n'écrit plus — il ne
    # trouvait donc plus rien, et son plancher a mordu. C'est exactement
    # ce qu'on lui demande : un axe qui cesse d'exister doit rougir, pas
    # se taire.
    "rayon": re.compile(r"\brounded-(?:box|field|selector|none|full)\b"),
    "décalage": re.compile(r"\bmt-\d+(?:\.\d+)?\b"),
}


def _panel_classes(theme: dict) -> str:
    return (theme.get("slots") or {}).get("panel", "") or ""


def _axis_values(axis: str) -> dict[str, str]:
    """``composant -> la valeur qu'il porte sur cet axe`` (absents ignorés)."""
    pattern = _AXES[axis]
    found: dict[str, str] = {}
    for name, theme in _PANELS.items():
        hit = pattern.search(_panel_classes(theme))
        if hit:
            found[name] = hit.group(0)
    return found


@pytest.mark.parametrize("axis", sorted(_AXES))
def test_anchored_panels_agree_on(axis: str) -> None:
    values = _axis_values(axis)
    assert values, f"aucun panneau ne porte l'axe {axis!r} — motif à revoir"
    distinct = set(values.values())
    assert len(distinct) == 1, (
        f"Les panneaux ancrés divergent sur « {axis} » : "
        f"{ {v: sorted(k for k, x in values.items() if x == v) for v in distinct} }\n"
        f"  Deux champs voisins dans un formulaire ouvrent des panneaux "
        f"qui ne se lisent plus comme une famille — et `select/theme.py` "
        f"déclare précisément l'inverse (« toute retouche ici va en "
        f"paire »).\n"
        f"  Si la différence est VOULUE, elle doit être argumentée dans le "
        f"thème et l'entrée retirée de `_PANELS` — pas laissée en dérive "
        f"silencieuse."
    )


def test_every_anchored_panel_declares_a_panel_slot() -> None:
    """Garde-fou : un thème sans slot ``panel`` rendrait la gate aveugle."""
    missing = [n for n, t in _PANELS.items() if not _panel_classes(t)]
    assert not missing, (
        f"{missing} n'ont pas de slot `panel` — soit le nom du slot a "
        f"changé, soit ils ne sont plus des panneaux ancrés. Dans les deux "
        f"cas la gate ne les couvre plus."
    )


def test_the_sweep_is_not_vacuous() -> None:
    """Plancher : les panneaux comparés existent encore.

    La gate compare des thèmes entre eux ; avec un seul panneau (ou
    zéro), « ils s'accordent » est vrai sans rien prouver.
    """
    assert len(_PANELS) >= 5, (
        f"seulement {len(_PANELS)} panneaux ancrés comparés (6 le "
        f"2026-08-19) — un accord entre moins de deux thèmes ne prouve rien."
    )
    assert len(_AXES) >= 3, (
        f"seulement {len(_AXES)} axes comparés (3 le 2026-08-19) — la "
        f"table des axes a rétréci, la gate compare moins qu'elle ne le dit."
    )


def test_the_detector_still_bites() -> None:
    """Mutation : les classes de panneau sont encore extraites d'un thème.

    La gate compare les panneaux ancrés entre eux, axe par axe. Si
    l'extraction cessait de rendre les classes, elle comparerait des
    chaînes vides — toutes égales, donc toutes d'accord.
    """
    theme = {"slots": {"panel": "absolute z-50 rounded-md border"}}
    assert "rounded-md" in _panel_classes(theme)
    assert _panel_classes({"slots": {}}) == "", (
        "un thème sans slot ``panel`` ne doit rien inventer"
    )
