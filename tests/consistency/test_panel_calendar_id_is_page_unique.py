"""Gate : le calendrier d'un picker est ADRESSÉ par son picker.

Ce que cette gate ferme
-----------------------
Le ``bz-id`` n'est pas décoratif : il indexe le magasin de scopes du
runtime (``03_scope.js``), une ``Map`` qui **survit à une navigation
``hx-boost``** puisque le runtime n'est pas rechargé.

Un composant construit pendant le ``render()`` d'un autre n'a pas son
constructeur sur la ``parent_stack`` — un picker n'est pas un conteneur,
il ne s'y empile jamais. L'``id`` du ``<bz-calendar>`` interne se dérivait
donc de ``"root"`` et valait ``root_calendar_0``, ``root_calendar_1``…
**identiques d'une page de picker à l'autre**.

Deux pages revendiquaient alors le même scope. Après un clic dans la
sidebar, le calendrier de la nouvelle page retrouvait celui de
l'ancienne, dont le parent est le picker de la page PRÉCÉDENTE : le
handler ``on_change`` écrivait sa valeur dans un scope mort. Grille
surlignée, champ vide, et un F5 pour s'en sortir. Le ``year`` / ``month``
fuyait par le même chemin, faisant apparaître le calendrier sur une année
qu'on n'avait pas choisie.

Aucune suite ne l'attrapait, et c'est structurel : **elles ne naviguent
pas**. Un composant monté puis cliqué sur une seule page se comporte
parfaitement. Le probe
``tests/runtime_js/test_boost_nav_keeps_pickers_live.py`` couvre l'autre
moitié — il navigue vraiment — mais il coûte un navigateur. Celui-ci
épingle l'invariant à la SOURCE, en une seconde et sans Chromium.

Pourquoi « préfixé par l'id du picker » et pas « unique »
---------------------------------------------------------
L'unicité au sein d'UNE page ne suffit pas : ``root_calendar_0`` est
parfaitement unique sur chaque page prise séparément, et c'est
exactement le bug. Ce qui doit tenir, c'est que l'id **dérive du
picker**, dont l'id porte lui le chemin de la page. C'est le seul énoncé
qui distingue le bon du mauvais cas.
"""

from __future__ import annotations

import re

import pytest

from bretzel.components.base.testing import render_isolated
from bretzel.components.inputs.date_picker import DatePicker
from bretzel.components.inputs.date_range_picker import DateRangePicker
from bretzel.components.inputs.month_picker import MonthPicker
from bretzel.components.inputs.week_picker import WeekPicker
from bretzel.core.serialize import serialize

#: Les quatre pickers qui montent un ``<bz-calendar>`` dans leur panneau.
#: En dur plutôt que découverts : un cinquième arrivant doit ATTERRIR
#: ici, et une découverte automatique le laisserait passer en silence.
_PICKERS = (DatePicker, DateRangePicker, WeekPicker, MonthPicker)

_CAL_BZ_ID = re.compile(r"<bz-calendar[^>]*\bbz-id=\"([^\"]+)\"")


def _rendered(cls: type) -> tuple[str, str]:
    """``(id du picker, id du calendrier interne)``."""
    with render_isolated():
        component = cls()
        html = serialize(component.render())
    match = _CAL_BZ_ID.search(html)
    assert match, (
        f"{cls.__name__} ne rend plus de ``<bz-calendar>`` porteur d'un "
        f"``bz-id`` — le motif de cette gate est périmé, répare-le avant "
        f"de croire qu'elle passe."
    )
    return component.id, match.group(1)


def test_the_picker_population_is_not_vacuous() -> None:
    """Le plancher : quatre pickers, chacun rendant un calendrier."""
    assert len(_PICKERS) >= 4, "la population des pickers a rétréci"
    for cls in _PICKERS:
        _rendered(cls)   # lève si le calendrier ou son bz-id a disparu


@pytest.mark.parametrize("cls", _PICKERS, ids=lambda c: c.__name__)
def test_the_panel_calendar_id_derives_from_its_picker(cls: type) -> None:
    """L'id du calendrier interne descend de celui de son picker."""
    picker_id, calendar_id = _rendered(cls)

    assert calendar_id.startswith(f"{picker_id}_"), (
        f"{cls.__name__} rend son calendrier avec ``bz-id={calendar_id!r}``, "
        f"qui ne dérive pas de ``{picker_id!r}``.\n\n"
        "Un id qui ne descend pas du picker ne porte pas le chemin de la "
        "page : deux pages différentes revendiquent alors le même scope, "
        "et une navigation hx-boost (qui ne recharge pas le runtime) fait "
        "écrire le handler dans le scope de la page précédente. "
        "Construis le calendrier via ``_picker_field.panel_calendar``, qui "
        "pose l'id."
    )


def test_the_detector_still_bites() -> None:
    """Mutation : le ``bz-id`` d'un ``<bz-calendar>`` est encore lu.

    Sans lecture, la comparaison d'unicité porterait sur une liste vide
    — et deux pickers de la même page se partageraient un id, ce que la
    gate existe pour interdire.
    """
    html = '<div><bz-calendar mode="day" bz-id="root_calendar_0"></bz-calendar></div>'
    assert _CAL_BZ_ID.findall(html) == ["root_calendar_0"]
    assert not _CAL_BZ_ID.findall('<div bz-id="x"></div>'), "faux positif"
