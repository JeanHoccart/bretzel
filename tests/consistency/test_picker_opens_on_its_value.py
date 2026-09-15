"""Un picker seedé s'ouvre sur le mois de SA VALEUR, pas sur aujourd'hui.

Pourquoi cette gate existe (mesuré le 2026-08-19)
-------------------------------------------------
``Calendar`` sait dériver son mois initial : ``month=`` explicite, sinon
le mois de ``value``, sinon aujourd'hui (``calendar.py``). Mais les
quatre pickers qui l'embarquent ne lui passaient **pas** leur valeur —
seulement ``mode``, ``color``, ``size``, les bornes et le handler.

Résultat mesuré, pour un ``ui.date_picker(value=date(2026, 6, 15))`` un
19 août : ``<bz-calendar month="2026-08-01">``. Le panneau s'ouvrait sur
le mois COURANT, et le jour sélectionné n'était pas dans la grille — donc
invisible. Les quatre pickers avaient le défaut, à l'identique.

Le bug est **invisible en test unitaire figé** et **invisible tout un
mois par an** : tant que la valeur d'essai tombe dans le mois courant,
tout paraît juste. C'est ce qui l'a laissé passer, et c'est pourquoi
cette gate calcule la date d'essai à partir d'aujourd'hui.

Ce que la gate n'affirme pas
-----------------------------
Rien sur une valeur *liée* (``ClientBinding``) : au SSR elle n'a pas de
valeur, et c'est le ``bz-effect`` de miroir qui la pose côté client. Le
mois d'ouverture d'un picker lié reste donc celui du jour — limitation
connue, écrite ici plutôt que découverte deux fois.
"""

from __future__ import annotations

import datetime as dt
import re

from bretzel import ui
from bretzel.components.base.testing import render_isolated
from bretzel.core.serialize import serialize

#: Preuve de morsure : le contrôle vit dans ``test_the_detector_still_bites``.
MUTATION_PROOF = "test_the_detector_still_bites"

_CAL_TAG = re.compile(r"<bz-calendar[^>]*>")
_MONTH_ATTR = re.compile(r'\bmonth="([^"]*)"')

#: Une valeur d'essai qui n'est JAMAIS dans le mois courant — sinon la
#: gate serait verte un mois sur douze sans rien prouver.
SEED = (dt.date.today().replace(day=1) - dt.timedelta(days=40)).replace(day=15)


def _pickers() -> dict[str, object]:
    return {
        "date_picker": lambda: ui.date_picker(value=SEED),
        "month_picker": lambda: ui.month_picker(value=SEED.replace(day=1)),
        "week_picker": lambda: ui.week_picker(value=SEED),
        "date_range_picker": lambda: ui.date_range_picker(
            value=(SEED, SEED + dt.timedelta(days=5))
        ),
    }


def opened_month(build) -> str | None:
    """Le ``month=`` du ``<bz-calendar>`` que ce picker embarque."""
    with render_isolated():
        html = serialize(build().render())
    tag = _CAL_TAG.search(html)
    if tag is None:
        return None
    found = _MONTH_ATTR.search(tag.group(0))
    return found.group(1) if found else None


def offenders() -> list[str]:
    want = SEED.replace(day=1).isoformat()
    out = []
    for name, build in _pickers().items():
        got = opened_month(build)
        if got is None:
            out.append(f"{name} : aucun ``<bz-calendar month=…>`` rendu")
        elif got != want:
            out.append(f"{name} : ouvre sur {got}, la valeur est de {want}")
    return out


def test_the_sweep_is_not_vacuous() -> None:
    """Plancher : les quatre pickers rendent bien un calendrier."""
    assert len(_pickers()) == 4
    rendered = [n for n, b in _pickers().items() if opened_month(b) is not None]
    assert len(rendered) == 4, (
        f"seuls {rendered} embarquent un ``<bz-calendar month=…>`` — le "
        f"balayage est amputé, et « tous ouvrent sur leur valeur » serait "
        f"affirmé sur moins que les quatre."
    )
    assert SEED.month != dt.date.today().month, (
        "la date d'essai est tombée dans le mois courant : la gate ne "
        "distinguerait plus « suit la valeur » de « suit aujourd'hui »."
    )


def test_every_picker_opens_on_its_value() -> None:
    found = offenders()
    assert not found, (
        "Ces pickers s'ouvrent sur le mois COURANT au lieu du mois de leur "
        "valeur — le jour sélectionné n'est même pas dans la grille "
        "affichée :\n  " + "\n  ".join(found)
    )


def test_the_detector_still_bites() -> None:
    """Les deux versants, sur le mécanisme lui-même."""
    # Versant LICITE : sans valeur, ouvrir sur aujourd'hui est CORRECT.
    today_first = dt.date.today().replace(day=1).isoformat()
    assert opened_month(lambda: ui.date_picker()) == today_first

    # Versant qui MORD : un ``month=`` explicite gagne sur la valeur, donc
    # le détecteur lit bien l'attribut et pas une constante.
    other = (SEED.replace(day=1) - dt.timedelta(days=200)).replace(day=1)
    assert opened_month(
        lambda: ui.calendar(value=SEED, month=other)
    ) == other.isoformat()
