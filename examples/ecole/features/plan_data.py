"""features/plan_data — data: the rooms, the seats, the constraints.

``kind="data"``. It carries the EF-G rules that live in the data, and two
of them are MEASURED traps from the original application.

**Trap no. 6 — an aisle is a CORRIDOR, not a cell.** The "aisle" button
opens the passage on the WHOLE column, not on the one seat touched
(EF-G4). *"A passage open on three rows and closed on two looks like no
real room."* The storage stays per seat, the gesture is per column, and
it is :func:`basculer_allee` that holds the difference.

**Trap no. 7 — the aisle width describes the ROOM, not the cycle.** One
value per room (EF-G6). Hard-coding it per cycle is what had been done,
and it is wrong: two secondes do not have the same furniture.

**EF-G10 — the constraints are attached to the CLASS, not to the room.**
*"Re-entering them per room would be a chore doubled by a risk of
divergence."* A class taught in two rooms therefore has two plans and one
single set of constraints.
"""

from __future__ import annotations

import json
from datetime import date

from bretzel import Feature
from bretzel.state import AppState, field
from examples.ecole.core.db import execute, query, scalar
from examples.ecole.core.placement import rangees_du_gabarit
from examples.ecole.features.annees import garde_ecriture

#: How many versions are kept per room (EF-G13).
VERSIONS_GARDEES = 6

#: EF-G3's bounds: twelve rows and twelve seats at most.
MAX_RANGEES = 12
MAX_COLONNES = 12

#: The outline proposed by "trace the room" (EF-G2).
LARGEUR_ALLEE_DEFAUT = 60


class PlanRev(AppState):
    """The token the plan's zones watch.

    The same reason as ``appreciations_data.FichesRev``: a database write
    touches no typed state, so nothing re-renders without it.
    ``merge="add"`` so a simultaneous drop and distribution do not lose
    an increment.
    """

    rev: int = field(default=0, merge="add")


class ContraintesRev(AppState):
    """The RIGHT COLUMN's token — separations, front seats, versions.

    A second token and not one more dependency on :class:`PlanRev`: these
    are two surfaces that do not move together. Seating a pupil changes
    neither a pair to separate nor the list of versions; ticking "front"
    moves nobody.

    Measured on 2026-09-13 before the cut: emptying a seat sent back
    **248 kB**, including the whole column — thirty pupil buttons, the
    separations, the versions — redrawn for nothing, at every drag
    gesture. ``merge="add"``, the same reason as above.
    """

    rev: int = field(default=0, merge="add")


def salles_de(classe_id: int) -> list[dict]:
    """A class's rooms, in tab order (EF-G11)."""
    return query(
        "SELECT id, nom, ordre, demi_groupe, fige FROM salles_plan "
        "WHERE classe_id = ? ORDER BY ordre, id", (classe_id,))


def salle(salle_id: int) -> dict | None:
    lignes = query(
        "SELECT s.id, s.classe_id, s.nom, s.ordre, s.demi_groupe, s.fige, "
        "c.annee_id, c.cycle, c.code FROM salles_plan s "
        "JOIN classes c ON c.id = s.classe_id WHERE s.id = ?", (salle_id,))
    return lignes[0] if lignes else None


def places_de(salle_id: int) -> list[dict]:
    """A room's seats, with the pupil sitting there if there is one."""
    return query(
        """
        SELECT p.id, p.rangee, p.colonne, p.eleve_id, p.nouvelle_table,
               p.allee_avant, e.nom, e.prenom, e.amenagement, e.vue_fragile,
               e.gaucher
        FROM places p LEFT JOIN eleves e ON e.id = p.eleve_id
        WHERE p.salle_id = ? ORDER BY p.rangee, p.colonne
        """,
        (salle_id,),
    )


def contraintes_de(classe_id: int) -> dict:
    """The pairs to separate and the pupils to put at the front
    (EF-G10)."""
    return {
        "separations": [
            (r["eleve_a"], r["eleve_b"]) for r in query(
                "SELECT id, eleve_a, eleve_b FROM separations "
                "WHERE classe_id = ?", (classe_id,))
        ],
        "devants": {r["eleve_id"] for r in query(
            "SELECT eleve_id FROM devants WHERE classe_id = ?",
            (classe_id,))},
    }


def separations_nommees(classe_id: int) -> list[dict]:
    """The pairs to separate, with the names — for the screen."""
    return query(
        """
        SELECT s.id, a.nom AS nom_a, a.prenom AS prenom_a,
               b.nom AS nom_b, b.prenom AS prenom_b
        FROM separations s
        JOIN eleves a ON a.id = s.eleve_a
        JOIN eleves b ON b.id = s.eleve_b
        WHERE s.classe_id = ? ORDER BY a.nom COLLATE NOCASE
        """,
        (classe_id,),
    )


def versions_de(salle_id: int) -> list[dict]:
    return query(
        "SELECT id, nom, cree_le FROM versions_plan WHERE salle_id = ? "
        "ORDER BY id DESC", (salle_id,))


def gabarits() -> list[dict]:
    """The reusable room shapes (EF-G15) — with no class at all."""
    return query(
        "SELECT id, nom, rangees, allees, largeur_allee FROM gabarits_salle "
        "ORDER BY nom")


def premiere_salle(classe_id: int, annee_id: int) -> int:
    """A class's room, created on the fly if it has none (EF-G11).

    *"A class has no room until its plan has been opened: the first is
    created on the fly."* Without that, the screen would open on an empty
    state one would have to "initialise" — one more gesture answering no
    question.
    """
    existantes = salles_de(classe_id)
    if existantes:
        return existantes[0]["id"]
    garde_ecriture(annee_id)
    salle_id = execute(
        "INSERT INTO salles_plan (classe_id, nom, ordre, demi_groupe, fige) "
        "VALUES (?, 'Salle principale', 0, NULL, 0)", (classe_id,))
    tracer(salle_id, annee_id, [6, 6, 6, 6, 6], [3, 5],
           LARGEUR_ALLEE_DEFAUT)
    return salle_id


# ── The writes ───────────────────────────────────────────────────────

def tracer(salle_id: int, annee_id: int, longueurs: list[int],
           allees: list[int], largeur: int) -> None:
    """EF-G2 — *"the room is traced in a single gesture"*.

    Erases and redoes: it is an accepted reset, and the screen says so
    beforehand. Keeping the seated pupils while redrawing the room would
    give "half" kept seats, which is harder to understand than an empty
    grid.
    """
    garde_ecriture(annee_id)
    longueurs = [min(n, MAX_COLONNES) for n in longueurs[:MAX_RANGEES]]
    execute("DELETE FROM places WHERE salle_id = ?", (salle_id,))
    for place in rangees_du_gabarit(longueurs, allees, largeur):
        execute(
            "INSERT INTO places (salle_id, rangee, colonne, eleve_id, "
            "nouvelle_table, allee_avant) VALUES (?, ?, ?, NULL, 0, ?)",
            (salle_id, place["rangee"], place["colonne"],
             place["allee_avant"]))
    PlanRev().rev += 1


def allonger(salle_id: int, annee_id: int, rangee: int,
             delta: int) -> str | None:
    """EF-G3's ``−`` and ``+``. Returns a refusal, or ``None``.

    *"An occupied seat refuses to go."* The refusal is returned as a
    SENTENCE and not a boolean: the screen must say why, otherwise the
    button looks broken.
    """
    garde_ecriture(annee_id)
    places = [p for p in places_de(salle_id) if p["rangee"] == rangee]
    if delta > 0:
        if len(places) >= MAX_COLONNES:
            return f"Une rangée ne dépasse pas {MAX_COLONNES} places."
        largeur = max((p["allee_avant"] for p in places), default=0)
        execute(
            "INSERT INTO places (salle_id, rangee, colonne, eleve_id, "
            "nouvelle_table, allee_avant) VALUES (?, ?, ?, NULL, 0, 0)",
            (salle_id, rangee, len(places) + 1))
        del largeur
        PlanRev().rev += 1
        return None
    if not places:
        return None
    derniere = places[-1]
    if derniere["eleve_id"]:
        return (f"{derniere['prenom']} {derniere['nom']} est assis à cette "
                f"place. Déplacez-le avant de la retirer.")
    execute("DELETE FROM places WHERE id = ?", (derniere["id"],))
    PlanRev().rev += 1
    return None


def basculer_allee(salle_id: int, annee_id: int, colonne: int,
                   largeur: int) -> str | None:
    """EF-G4 — the passage opens on the WHOLE column, not on one seat.

    It is trap no. 6, and it fits in a ``WHERE`` clause: ``colonne = ?``
    and not ``id = ?``. *"Only the rows where the column aimed at exists
    move"* — which is true without doing anything, since the others have
    no row for that column.

    EF-G5: an aisle in front of the FIRST seat is refused.
    """
    garde_ecriture(annee_id)
    if colonne <= 1:
        return ("Une allée devant la première place ne sépare personne : "
                "elle décalerait la rangée entière.")
    actuelles = [p["allee_avant"] for p in places_de(salle_id)
                 if p["colonne"] == colonne]
    ouverte = any(actuelles)
    execute(
        "UPDATE places SET allee_avant = ? WHERE salle_id = ? AND colonne = ?",
        (0 if ouverte else largeur, salle_id, colonne))
    PlanRev().rev += 1
    return None


def regler_largeur(salle_id: int, annee_id: int, largeur: int) -> None:
    """EF-G6 — **a room has one passage, not ten widths.**"""
    garde_ecriture(annee_id)
    execute(
        "UPDATE places SET allee_avant = ? WHERE salle_id = ? "
        "AND allee_avant > 0", (max(0, min(largeur, 200)), salle_id))
    PlanRev().rev += 1


def asseoir(salle_id: int, annee_id: int, place_id: int,
            eleve_id: int | None) -> None:
    """Put a pupil on a seat — and SWAP if it is taken.

    EF-G8 asks for four gestures (drag, empty, empty all, swap); three of
    them are this same call. The swap is not a special case: a pupil
    dropped on an occupied seat has to go somewhere, and the place they
    came from is the only free one.
    """
    garde_ecriture(annee_id)
    if eleve_id is None:
        execute("UPDATE places SET eleve_id = NULL WHERE id = ?", (place_id,))
        PlanRev().rev += 1
        return
    ancienne = query(
        "SELECT id FROM places WHERE salle_id = ? AND eleve_id = ?",
        (salle_id, eleve_id))
    occupant = query("SELECT eleve_id FROM places WHERE id = ?", (place_id,))
    deja = occupant[0]["eleve_id"] if occupant else None
    execute("UPDATE places SET eleve_id = ? WHERE id = ?",
            (eleve_id, place_id))
    if ancienne:
        execute("UPDATE places SET eleve_id = ? WHERE id = ?",
                (deja, ancienne[0]["id"]))
    PlanRev().rev += 1


def tout_vider(salle_id: int, annee_id: int) -> None:
    garde_ecriture(annee_id)
    execute("UPDATE places SET eleve_id = NULL WHERE salle_id = ?",
            (salle_id,))
    PlanRev().rev += 1


def appliquer(salle_id: int, annee_id: int,
              assises: dict[int, int]) -> None:
    """Write a whole distribution."""
    garde_ecriture(annee_id)
    execute("UPDATE places SET eleve_id = NULL WHERE salle_id = ?",
            (salle_id,))
    for place_id, eleve_id in assises.items():
        execute("UPDATE places SET eleve_id = ? WHERE id = ?",
                (eleve_id, place_id))
    PlanRev().rev += 1


def figer(salle_id: int, annee_id: int, fige: bool) -> None:
    """EF-G14 — **the plan freezes, and the state is KEPT**.

    *"On a tablet, the hand holding the device brushes the screen and
    moves a pupil with nothing to flag it — one notices at the next
    lesson, in front of a false plan."* The state lives in the database
    and not in a session: *"one freezes once for the year, not every
    hour"*.
    """
    garde_ecriture(annee_id)
    execute("UPDATE salles_plan SET fige = ? WHERE id = ?",
            (int(fige), salle_id))
    PlanRev().rev += 1


def ajouter_salle(classe_id: int, annee_id: int, nom: str,
                  demi_groupe: int | None) -> int:
    """A second room for the same class (EF-G11)."""
    garde_ecriture(annee_id)
    ordre = (scalar("SELECT COALESCE(MAX(ordre), -1) FROM salles_plan "
                    "WHERE classe_id = ?", (classe_id,)) or 0) + 1
    salle_id = execute(
        "INSERT INTO salles_plan (classe_id, nom, ordre, demi_groupe, fige) "
        "VALUES (?, ?, ?, ?, 0)",
        (classe_id, nom.strip()[:40] or "Nouvelle salle", ordre,
         demi_groupe))
    tracer(salle_id, annee_id, [6, 6, 6, 6], [3, 5], LARGEUR_ALLEE_DEFAUT)
    return salle_id


def supprimer_salle(salle_id: int, annee_id: int) -> str | None:
    """EF-G11 — **the LAST room cannot be deleted.**

    *""Erase the grid" already exists to start over."* A class with no
    room at all would reopen its plan on an on-the-fly creation, so the
    deletion would have deleted nothing — just lost the seats.
    """
    garde_ecriture(annee_id)
    donnees = salle(salle_id)
    if donnees is None:
        return None
    if len(salles_de(donnees["classe_id"])) <= 1:
        return ("C'est la dernière salle de cette classe. Pour repartir de "
                "zéro, utilisez « Tracer la salle ».")
    execute("DELETE FROM places WHERE salle_id = ?", (salle_id,))
    execute("DELETE FROM versions_plan WHERE salle_id = ?", (salle_id,))
    execute("DELETE FROM salles_plan WHERE id = ?", (salle_id,))
    PlanRev().rev += 1
    return None


def figer_version(salle_id: int, annee_id: int, nom: str) -> None:
    """EF-G13 — one freezes a plan, six are kept per room."""
    garde_ecriture(annee_id)
    photo = [
        {"rangee": p["rangee"], "colonne": p["colonne"],
         "eleve_id": p["eleve_id"], "allee_avant": p["allee_avant"]}
        for p in places_de(salle_id)
    ]
    execute(
        "INSERT INTO versions_plan (salle_id, nom, cree_le, contenu) "
        "VALUES (?, ?, ?, ?)",
        (salle_id, nom.strip()[:40] or date.today().isoformat(),
         date.today().isoformat(), json.dumps(photo)))
    execute(
        "DELETE FROM versions_plan WHERE salle_id = ? AND id NOT IN "
        "(SELECT id FROM versions_plan WHERE salle_id = ? "
        " ORDER BY id DESC LIMIT ?)",
        (salle_id, salle_id, VERSIONS_GARDEES))
    ContraintesRev().rev += 1


def restaurer_version(version_id: int, annee_id: int) -> None:
    garde_ecriture(annee_id)
    lignes = query("SELECT salle_id, contenu FROM versions_plan WHERE id = ?",
                   (version_id,))
    if not lignes:
        return
    salle_id = lignes[0]["salle_id"]
    execute("DELETE FROM places WHERE salle_id = ?", (salle_id,))
    for place in json.loads(lignes[0]["contenu"]):
        execute(
            "INSERT INTO places (salle_id, rangee, colonne, eleve_id, "
            "nouvelle_table, allee_avant) VALUES (?, ?, ?, ?, 0, ?)",
            (salle_id, place["rangee"], place["colonne"], place["eleve_id"],
             place["allee_avant"]))
    PlanRev().rev += 1


def supprimer_version(version_id: int, annee_id: int) -> None:
    garde_ecriture(annee_id)
    execute("DELETE FROM versions_plan WHERE id = ?", (version_id,))
    ContraintesRev().rev += 1


def poser_separation(classe_id: int, annee_id: int, eleve_a: int,
                     eleve_b: int) -> None:
    garde_ecriture(annee_id)
    if eleve_a == eleve_b:
        return
    execute(
        "INSERT INTO separations (classe_id, eleve_a, eleve_b) "
        "VALUES (?, ?, ?)", (classe_id, eleve_a, eleve_b))
    ContraintesRev().rev += 1


def retirer_separation(separation_id: int, annee_id: int) -> None:
    garde_ecriture(annee_id)
    execute("DELETE FROM separations WHERE id = ?", (separation_id,))
    ContraintesRev().rev += 1


def basculer_devant(classe_id: int, annee_id: int, eleve_id: int) -> None:
    """EF-G9's MANUAL CHOICE — which adds up with the accommodation and
    the fragile eyesight, it does not replace them."""
    garde_ecriture(annee_id)
    deja = query(
        "SELECT id FROM devants WHERE classe_id = ? AND eleve_id = ?",
        (classe_id, eleve_id))
    if deja:
        execute("DELETE FROM devants WHERE id = ?", (deja[0]["id"],))
    else:
        execute("INSERT INTO devants (classe_id, eleve_id) VALUES (?, ?)",
                (classe_id, eleve_id))
    ContraintesRev().rev += 1


def regler_demi_groupe(eleve_id: int, annee_id: int, classe_id: int,
                       groupe: int | None) -> None:
    """EF-G17 — split the class into two practical half-groups."""
    garde_ecriture(annee_id)
    execute(
        "UPDATE inscriptions SET demi_groupe = ? WHERE eleve_id = ? "
        "AND classe_id = ? AND fin IS NULL", (groupe, eleve_id, classe_id))
    # BOTH: the half-group changes who the room seats *and* who the
    # constraints column offers to put at the front.
    PlanRev().rev += 1
    ContraintesRev().rev += 1


feature = Feature(
    name="plan_data",
    kind="data",
    provides=[
        PlanRev, ContraintesRev, salles_de, salle, places_de, contraintes_de,
        separations_nommees, versions_de, gabarits, premiere_salle, tracer,
        allonger, basculer_allee, regler_largeur, asseoir, tout_vider,
        appliquer, figer, ajouter_salle, supprimer_salle, figer_version,
        restaurer_version, supprimer_version, poser_separation,
        retirer_separation, basculer_devant, regler_demi_groupe,
    ],
    uses=["db", "annees"],
)
