"""core/placement — seating a class. Pure Python, testable alone.

EF-G7 and EF-G9. Two things, and the second is the application's only
one entitled to be random.

EF-G9 — the distribution, in the order the specification writes it
-------------------------------------------------------------------
1. **the pupils to put at the front first**, in the first two rows,
   *preferably the first* — whether they are there for an accommodation,
   fragile eyesight or a manual choice: **all three add up**;
2. **the very first filling**: in alphabetical order, starting from the
   BACK of the room. *"It is predictable, and a first plan has no reason
   yet to be shuffled."*;
3. **otherwise**: a random draw, several attempts to avoid seating two
   pupils to be separated side by side.

**Never a blocking failure.** At worst, the draw violating the fewest
pairs is kept, and the remaining conflicts are REPORTED. A plan one
refuses to produce leaves the teacher with no plan at all; an imperfect
plan that says so is corrected in two drags.

EF-G7 — a desk is COMPUTED, not entered
----------------------------------------
*"A desk is two pupils side by side: they share a row with consecutive
columns."* There is no "desk" entity (EF-G1); the aisle that separates is
what cuts.
"""

from __future__ import annotations

import random
from itertools import pairwise

#: How many draws are attempted before keeping the least bad.
#: Twenty: beyond that, the gain measured on thirty pupils and three
#: pairs is nil, and the gesture must stay instant.
ESSAIS = 20

#: Up to which row "front" means front (EF-G9).
RANGEES_DEVANT = 2


def tables_de(places: list[dict]) -> list[tuple[int, int]]:
    """The ``(seat_a, seat_b)`` pairs that form a desk (EF-G7).

    Two seats make a desk when they are on the SAME row, at consecutive
    columns, and **no aisle separates them**: it is the aisle that cuts,
    since there is no "desk" entity.
    """
    par_rangee: dict[int, list[dict]] = {}
    for place in places:
        par_rangee.setdefault(place["rangee"], []).append(place)

    paires: list[tuple[int, int]] = []
    for rangee in par_rangee.values():
        rangee.sort(key=lambda p: p["colonne"])
        for gauche, droite in pairwise(rangee):
            if droite["colonne"] != gauche["colonne"] + 1:
                continue
            if droite["allee_avant"]:
                continue
            paires.append((gauche["id"], droite["id"]))
    return paires


def voisins_de(places: list[dict]) -> dict[int, set[int]]:
    """``seat → seats sharing its desk`` — the entry to the conflicts."""
    voisins: dict[int, set[int]] = {p["id"]: set() for p in places}
    for gauche, droite in tables_de(places):
        voisins[gauche].add(droite)
        voisins[droite].add(gauche)
    return voisins


def conflits(assises: dict[int, int], places: list[dict],
             separations: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """The pairs to separate that end up at the same desk anyway.

    ``assises``: ``place_id → eleve_id``. Returns the conflicting PUPIL
    pairs, not the seats: it is what the screen must name.
    """
    par_place = voisins_de(places)
    a_separer = {frozenset(paire) for paire in separations}
    trouves: set[frozenset] = set()
    for place_id, eleve_id in assises.items():
        for voisin in par_place.get(place_id, ()):
            autre = assises.get(voisin)
            if autre and frozenset({eleve_id, autre}) in a_separer:
                trouves.add(frozenset({eleve_id, autre}))
    return [tuple(sorted(paire)) for paire in trouves]


def repartir(
    *,
    eleves: list[dict],
    places: list[dict],
    devants: set[int],
    separations: list[tuple[int, int]],
    premier_remplissage: bool,
    graine: int | None = None,
) -> dict[int, int]:
    """Seat the class. Returns ``place_id → eleve_id``.

    ``eleves`` must carry ``id``, ``nom``, ``prenom``, ``amenagement``,
    ``vue_fragile`` — the three reasons for being at the front ADD UP
    with ``devants``' manual choice.

    ``graine`` makes the draw reproducible; it is what allows testing
    "at worst, the least bad" without writing a test that passes one
    time in three.
    """
    libres = sorted(places, key=lambda p: (p["rangee"], p["colonne"]))
    if not libres or not eleves:
        return {}

    a_devant = [
        e for e in eleves
        if e["id"] in devants or e.get("amenagement")
        or e.get("vue_fragile")
    ]
    autres = [e for e in eleves if e not in a_devant]

    # The front seats, the first row FIRST — it is EF-G9's "preferably
    # the first".
    devant = [p for p in libres if p["rangee"] <= RANGEES_DEVANT]
    reste = [p for p in libres if p["rangee"] > RANGEES_DEVANT]

    if premier_remplissage:
        # *"In alphabetical order, starting from the back of the
        # room."* Predictable, and a first plan has no reason to be
        # shuffled.
        autres = sorted(autres, key=lambda e: (e["nom"].lower(),
                                               e["prenom"].lower()))
        reste = sorted(reste, key=lambda p: (-p["rangee"], p["colonne"]))
        return asseoir_les_deux_groupes(a_devant, autres, devant, reste)

    tirage = random.Random(graine)
    meilleur: dict[int, int] = {}
    meilleur_cout = None
    for _ in range(ESSAIS):
        melanges = list(autres)
        tirage.shuffle(melanges)
        devant_melange = list(a_devant)
        tirage.shuffle(devant_melange)
        essai = asseoir_les_deux_groupes(devant_melange, melanges, devant, reste)
        cout = len(conflits(essai, places, separations))
        if meilleur_cout is None or cout < meilleur_cout:
            meilleur, meilleur_cout = essai, cout
        if cout == 0:
            break
    return meilleur


def asseoir_les_deux_groupes(
    a_devant: list[dict], autres: list[dict],
    devant: list[dict], reste: list[dict],
) -> dict[int, int]:
    """Place both groups on the two sets of seats, in order.

    ⚠️ **The bulk of the class starts from the BACK, not the front**, and
    it is what distinguishes this function from a naive filling. EF-G9
    says two things at once: those who must be at the front go there,
    and *"the very first filling is done in alphabetical order **starting
    from the back of the room**"*. A first version seated everybody
    starting from the first row: it gave the right alphabetical ORDER and
    the wrong HALF of the room, which does not show in a list and leaps
    out on a plan.

    The overflows cross over, and we never refuse to seat: what does not
    fit at the front goes to the back, what does not fit at the back
    comes forward.
    """
    assises: dict[int, int] = {}
    file_devant = list(a_devant)
    file_autres = list(autres)

    for place in devant:
        if not file_devant:
            break
        assises[place["id"]] = file_devant.pop(0)["id"]

    for place in reste:
        if not file_autres:
            break
        assises[place["id"]] = file_autres.pop(0)["id"]

    # Whoever is left standing takes the seats still free, wherever
    # they are. The front overflow goes first: it stays nearer the board
    # than if it started right at the back.
    en_attente = file_devant + file_autres
    for place in [*devant, *reste]:
        if not en_attente:
            break
        if place["id"] in assises:
            continue
        assises[place["id"]] = en_attente.pop(0)["id"]
    return assises


def rangees_du_gabarit(longueurs: list[int], allees: list[int],
                       largeur: int) -> list[dict]:
    """EF-G2's outline: ``[{rangee, colonne, allee_avant}, …]``.

    ``allees`` gives the COLUMNS in front of which the passage opens —
    and it is trap no. 6: *"an aisle is a CORRIDOR, not a cell"*. The
    storage stays per seat; the decision is per column, so it applies to
    every row where that column exists (EF-G4).

    **Column 1 is refused** (EF-G5): an aisle in front of the first seat
    separates nobody and would shift the whole row.
    """
    ouvertes = {c for c in allees if c > 1}
    tracé: list[dict] = []
    for rangee, longueur in enumerate(longueurs, start=1):
        for colonne in range(1, longueur + 1):
            tracé.append({
                "rangee": rangee,
                "colonne": colonne,
                # EF-G6: the width holds for the WHOLE room — a room
                # has one passage, not ten widths.
                "allee_avant": largeur if colonne in ouvertes else 0,
            })
    return tracé
