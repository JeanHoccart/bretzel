"""``ui.calendar(marks=…)`` — le contrat Python.

Ce que `marks=` est, et ce qu'il n'est pas
-------------------------------------------
Un **sélecteur** qui sait dire « il se passe quelque chose ce jour-là ».
C'est le vocabulaire normal de la famille (``modifiers`` chez
react-day-picker, ``slots.day`` chez MUI, ``renderDay`` chez Mantine) —
pas le début d'un agenda. Les vues semaine/jour, les créneaux horaires et
les chevauchements sont un AUTRE composant, ``ui.event_calendar``, que
``bretzel describe`` annonce depuis juin 2026.

Pourquoi une prop de DONNÉES et pas un slot de cellule
--------------------------------------------------------
Ce n'est pas un choix esthétique : la grille est bâtie **en JavaScript**
par le custom element — le serveur n'envoie qu'un conteneur vide. Un slot
Python n'a donc structurellement aucun moyen d'atteindre une case. Un
dictionnaire sérialisé en attribut, si : c'est déjà exactement le chemin
de ``disabled_dates``.

Le versant navigateur — la pastille est visible, elle ne décale pas le
numéro du jour, et elle survit au changement de mois — est dans
``tests/probes/probe_calendar_marks.py``. Ici on ne juge que ce qui est
déterministe : la normalisation, les refus, et ce qui part sur le fil.
"""

from __future__ import annotations

import datetime as dt
import json
import re

import pytest

from bretzel.components.base.attrs import ComponentDefinitionError
from bretzel.components.base.testing import render_isolated
from bretzel.components.inputs.calendar import Calendar
from bretzel.components.inputs.calendar.calendar import normalise_marks
from bretzel.core.serialize import serialize

DAY = dt.date(2026, 8, 14)
OTHER = dt.date(2026, 8, 20)


def render(**kwargs) -> str:
    with render_isolated():
        return serialize(Calendar(value=DAY, **kwargs).render())


def attribute(html: str, name: str) -> str | None:
    found = re.search(rf'\b{name}="([^"]*)"', html)
    return found.group(1) if found else None


# ── Les deux formes d'appel ───────────────────────────────────────────

def test_a_plain_list_means_one_each() -> None:
    """La forme courte : « ces jours-là ont quelque chose »."""
    assert normalise_marks([DAY, OTHER]) == {"2026-08-14": 1, "2026-08-20": 1}


def test_a_mapping_carries_the_count() -> None:
    assert normalise_marks({DAY: 3, OTHER: 1}) == {"2026-08-14": 3, "2026-08-20": 1}


def test_iso_strings_are_accepted_like_dates() -> None:
    assert normalise_marks(["2026-08-14"]) == {"2026-08-14": 1}
    assert normalise_marks({"2026-08-14": 2}) == {"2026-08-14": 2}


def test_nothing_means_nothing() -> None:
    for empty in (None, [], {}, ()):
        assert normalise_marks(empty) == {}


def test_a_zero_count_removes_the_mark() -> None:
    """Un dictionnaire construit par un ``Counter`` en contient.

    Lever dessus obligerait chaque appelant à le filtrer avant de le
    passer, pour un cas qui a une réponse évidente : pas de marque.
    """
    assert normalise_marks({DAY: 0, OTHER: 2}) == {"2026-08-20": 2}


def test_the_output_is_sorted() -> None:
    """L'ordre est stable, donc le HTML rendu l'est aussi — un attribut
    qui change d'ordre à chaque rendu ferait mentir tout diff d'octets."""
    scrambled = {OTHER: 1, DAY: 1}
    assert list(normalise_marks(scrambled)) == ["2026-08-14", "2026-08-20"]


# ── Les refus ─────────────────────────────────────────────────────────

def test_a_string_that_is_not_a_date_raises() -> None:
    """``date_to_iso`` rend une chaîne TELLE QUELLE — c'est ce qui laisse
    passer un binding client ailleurs, et c'est voulu là-bas. Ici la clé
    indexe une case : une chaîne libre ne correspondrait à rien, en
    silence."""
    with pytest.raises(ComponentDefinitionError, match="is not a date"):
        normalise_marks(["mardi prochain"])


def test_a_loosely_formatted_date_raises() -> None:
    with pytest.raises(ComponentDefinitionError, match="is not a date"):
        normalise_marks(["2026-8-4"])


def test_a_boolean_count_raises() -> None:
    """``bool`` EST un ``int`` en Python, et ``{jour: True}`` est une
    faute de frappe crédible pour ``[jour]``. La laisser passer
    afficherait « 1 » sans que personne l'ait voulu."""
    with pytest.raises(ComponentDefinitionError, match="must be an integer"):
        normalise_marks({DAY: True})


def test_a_negative_count_raises() -> None:
    with pytest.raises(ComponentDefinitionError, match="negative count"):
        normalise_marks({DAY: -1})


def test_a_float_count_raises() -> None:
    with pytest.raises(ComponentDefinitionError, match="must be an integer"):
        normalise_marks({DAY: 1.5})


# ── Ce qui part sur le fil ────────────────────────────────────────────

def test_no_marks_emits_no_attribute() -> None:
    """Un attribut vide coûterait des octets sur chaque calendrier du
    dépôt pour ne rien dire."""
    html = render()
    assert attribute(html, "marks") is None
    assert "data-bz-mark-label" not in html


def test_marks_travel_as_json_on_the_root() -> None:
    html = render(marks={DAY: 3})
    assert json.loads(attribute(html, "marks").replace("&quot;", '"')) == {
        "2026-08-14": 3,
    }


def test_the_accessible_name_template_travels_resolved() -> None:
    """Le gabarit est résolu CÔTÉ SERVEUR puis substitué par le runtime.

    La grille est bâtie en JavaScript et la table des mots du framework
    n'existe qu'en Python : sans ce passage, une case marquée
    s'annoncerait en anglais quelle que soit la langue de l'app.
    """
    html = render(marks={DAY: 3})
    assert attribute(html, "data-bz-mark-label") == "{day}, {n} events"


def test_the_grid_container_stays_empty_at_ssr() -> None:
    """La marque ne change pas le partage : les cases restent bâties par
    le custom element. Un jour marqué qui apparaîtrait dans le HTML
    voudrait dire qu'on a deux chemins de rendu pour la même grille."""
    html = render(marks={DAY: 3})
    assert "data-day-cell" not in html
