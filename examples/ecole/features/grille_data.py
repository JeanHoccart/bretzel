"""features/grille_data — data: the typical grid, its exceptions, its
way back.

``kind="data"``. It answers **one** compound question: *what do we see in
the week of such and such?* — and the answer mixes three sources the
specification orders explicitly (EF-K5):

1. the **typical grid**, repeating per day × time slot × week A/B;
2. the **exceptional hours**, set on REAL dates, and which win: an extra
   hour, or a cancellation;
3. the **periods without class**, which empty a whole day (EF-B4).

*"The log reads the result of the grid AND the exceptions, never the grid
alone — otherwise it would offer to record a class that did not take
place"*: that is why :func:`semaine_affichee` is the only door, and why
batch 9 will reuse it as is.

The way back (EF-B12)
----------------------
The whole grid is set aside **before every modification**, as JSON, and
the last twenty are kept. Restoring rewrites the slots — except those
whose class has disappeared in the meantime: *"a deleted class does not
come back to life: its cell is lost, the rest returns"*. It is the only
form that does not recreate data from a snapshot.
"""

from __future__ import annotations

import json
from datetime import date, timedelta

from bretzel import Feature
from examples.ecole.core.db import execute, query
from examples.ecole.core.domain import (
    blocs_du_jour,
    cycle_propose,
    lire_saisie,
    niveau_du_code,
    periode_sans_classe,
    rang_du_niveau,
    semaine_ab,
)
from examples.ecole.features.annees import garde_ecriture

#: How many previous grids are kept (§ 5.4). Twenty is a whole
#: timetable-revision session — beyond that, one is no longer going
#: "back", one is restoring an old version, and it is not the same
#: gesture.
GRILLES_GARDEES = 20


def codes_de_lannee(annee_id: int) -> frozenset[str]:
    """The existing class codes — EF-B8's input.

    It is this list that decides whether "2nde - 4" is split or stays
    whole. It is re-read at every entry: a class created at the previous
    cell must be recognised at the next.
    """
    return frozenset(
        r["code"] for r in query(
            "SELECT code FROM classes WHERE annee_id = ?", (annee_id,))
    )


def lundi_affiche(annee: dict, demande: str) -> date:
    """The Monday of the week to show — the one asked for, or today's.

    A request outside the year is brought back inside it: a link shared
    from one year to the next then opens the first week rather than an
    empty grid with no explanation.
    """
    debut = date.fromisoformat(annee["debut"])
    fin = date.fromisoformat(annee["fin"])
    if demande:
        try:
            voulu = date.fromisoformat(demande)
        except ValueError:
            voulu = date.today()
    else:
        voulu = date.today()
    voulu = min(max(voulu, debut), fin)
    return voulu - timedelta(days=voulu.weekday())


def semaine_affichee(annee: dict, lundi: date) -> dict:
    """Everything a week's grid must know, in one read.

    Returns ``{"lettre", "jours": [{date, periode, blocs}], "bornes"}``.

    ⚠️ **``lettre`` may be ``None``**, and the screen must SAY so rather
    than show "A" (RT-4). Without a reference date, the typical grid is
    not readable at all: we do not know which week we are looking at.
    """
    lundi_ref = (date.fromisoformat(annee["lundi_ref"])
                 if annee["lundi_ref"] else None)
    lettre = semaine_ab(lundi, lundi_ref)

    bornes = {
        r["rang"]: (r["debut"], r["fin"])
        for r in query(
            "SELECT rang, debut, fin FROM horaires WHERE annee_id = ? "
            "ORDER BY rang", (annee["id"],))
    }
    periodes = [
        (r["libelle"], date.fromisoformat(r["debut"]),
         date.fromisoformat(r["fin"]))
        for r in query("SELECT libelle, debut, fin FROM vacances "
                       "WHERE annee_id = ?", (annee["id"],))
    ]

    # The typical grid of the week shown. With no letter, there is
    # nothing to read: we return empty days rather than invent half.
    typiques: dict[tuple[int, int], dict] = {}
    if lettre:
        for ligne in query(
            "SELECT cr.jour, h.rang, c.code, cr.nature, cr.salle "
            "FROM creneaux cr "
            "JOIN horaires h ON h.id = cr.horaire_id "
            "JOIN classes c ON c.id = cr.classe_id "
            "WHERE cr.annee_id = ? AND cr.semaine = ?",
            (annee["id"], lettre),
        ):
            typiques[(ligne["jour"], ligne["rang"])] = {
                "code": ligne["code"], "nature": ligne["nature"],
                "salle": ligne["salle"], "exception": False,
            }

    # THOSE dates' exceptions. They win: a class sets an extra hour, a
    # row with no class cancels it (EF-B11).
    samedi = lundi + timedelta(days=5)
    exceptions: dict[tuple[str, int], dict | None] = {}
    for ligne in query(
        "SELECT e.jour, h.rang, c.code, e.salle FROM heures_exceptionnelles e "
        "JOIN horaires h ON h.id = e.horaire_id "
        "LEFT JOIN classes c ON c.id = e.classe_id "
        "WHERE e.annee_id = ? AND e.jour BETWEEN ? AND ?",
        (annee["id"], lundi.isoformat(), samedi.isoformat()),
    ):
        exceptions[(ligne["jour"], ligne["rang"])] = (
            {"code": ligne["code"], "nature": "", "salle": ligne["salle"],
             "exception": True}
            if ligne["code"] else None
        )

    # What is already recorded in the lesson log, for EF-B13's badge.
    # The list covers ONLY the week shown — keeping it for the whole year
    # would cost a hundred and fifty rows for six.
    consignees = {
        (r["date"], r["code"])
        for r in query(
            "SELECT ca.date, c.code FROM cahier ca "
            "JOIN classes c ON c.id = ca.classe_id "
            "WHERE ca.date BETWEEN ? AND ? AND c.annee_id = ?",
            (lundi.isoformat(), samedi.isoformat(), annee["id"]),
        )
    }

    jours = []
    for index in range(6):
        jour = lundi + timedelta(days=index)
        iso = jour.isoformat()
        cases: dict[int, dict] = {}
        for rang in bornes:
            case = exceptions.get((iso, rang), _MANQUE)
            if case is _MANQUE:
                case = typiques.get((index, rang))
            if case is not None:
                cases[rang] = dict(case)
        blocs = blocs_du_jour(cases, bornes)
        for bloc in blocs:
            bloc["consignee"] = (iso, bloc["code"]) in consignees
            # ⚠️ The EXCEPTION flag is glued back on HERE, after the
            # merge, and it was missing for an hour: ``blocs_du_jour``
            # builds a NEW dict (debut / fin / code / nature / salles)
            # and has no reason to know about the exceptions — it is a
            # calendar rule, not a block-building one. Without this
            # regluing, ``bloc["exception"]`` was always absent and an
            # hour set by hand rendered exactly like an ordinary lesson.
            # Found by the probe, not by re-reading: both forms produce
            # valid HTML.
            bloc["exception"] = any(
                cases[rang].get("exception")
                for rang in range(bloc["debut"], bloc["fin"] + 1)
                if rang in cases
            )
        jours.append({
            "date": jour,
            "periode": periode_sans_classe(jour, periodes),
            "cases": cases,
            "blocs": blocs,
        })

    return {"lettre": lettre, "jours": jours, "bornes": bornes}


#: Sentinel: an exception that CANCELS is a legitimate ``None``, so
#: ``None`` cannot mean "no exception here".
_MANQUE = object()


# ── The writes ───────────────────────────────────────────────────────

def creer_classe_vide(annee_id: int, code: str) -> int:
    """EF-B6 — *"an unknown code creates the class, empty"*.

    *The timetable arrives at the end of August, the pupil lists at the
    start of term*: refusing an unknown code would force creating ten
    classes by hand before being able to enter the first hour.

    The cycle and the level are PROPOSED from the code (RT-3), once,
    here — and correctable afterwards in the class's screen.
    """
    garde_ecriture(annee_id)
    niveau = niveau_du_code(code)
    rang = rang_du_niveau(niveau) * 10
    return execute(
        "INSERT INTO classes (annee_id, code, libelle, cycle, niveau, rang) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (annee_id, code, code, cycle_propose(niveau), niveau, rang),
    )


def sauver_grille(annee_id: int) -> None:
    """Set the whole grid aside, BEFORE a modification (EF-B12).

    The snapshot carries the class CODES, not their identifiers: it is
    what lets the restore cleanly skip a class deleted in the meantime,
    instead of stumbling on a dead foreign key.
    """
    photo = query(
        "SELECT cr.jour, h.rang, cr.semaine, c.code, cr.nature, cr.salle "
        "FROM creneaux cr "
        "JOIN horaires h ON h.id = cr.horaire_id "
        "JOIN classes c ON c.id = cr.classe_id "
        "WHERE cr.annee_id = ?",
        (annee_id,),
    )
    execute(
        "INSERT INTO grilles_precedentes (annee_id, pose_le, contenu) "
        "VALUES (?, ?, ?)",
        (annee_id, date.today().isoformat(), json.dumps(photo)),
    )
    execute(
        "DELETE FROM grilles_precedentes WHERE annee_id = ? AND id NOT IN "
        "(SELECT id FROM grilles_precedentes WHERE annee_id = ? "
        " ORDER BY id DESC LIMIT ?)",
        (annee_id, annee_id, GRILLES_GARDEES),
    )


def poser_case(annee_id: int, jour: int, rang: int, semaine: str,
               saisie: str) -> str:
    """Set (or clear) a cell of the TYPICAL grid. Returns the code kept.

    The whole entry goes through
    :func:`~examples.ecole.core.domain.lire_saisie` — the split into
    class / nature / room is a domain rule, not a screen detail, and it
    is trap no. 1.
    """
    garde_ecriture(annee_id)
    sauver_grille(annee_id)
    code, nature, salle = lire_saisie(saisie, codes_de_lannee(annee_id))
    if not code:
        execute(
            "DELETE FROM creneaux WHERE annee_id = ? AND jour = ? "
            "AND semaine = ? AND horaire_id = "
            "(SELECT id FROM horaires WHERE annee_id = ? AND rang = ?)",
            (annee_id, jour, semaine, annee_id, rang),
        )
        return ""

    classe_id = classe_id_de(annee_id, code)
    if classe_id is None:
        classe_id = creer_classe_vide(annee_id, code)
    execute(
        "INSERT INTO creneaux "
        "(annee_id, jour, horaire_id, semaine, classe_id, nature, salle) "
        "VALUES (?, ?, "
        " (SELECT id FROM horaires WHERE annee_id = ? AND rang = ?), "
        " ?, ?, ?, ?) "
        "ON CONFLICT (annee_id, jour, horaire_id, semaine) DO UPDATE SET "
        "classe_id = excluded.classe_id, nature = excluded.nature, "
        "salle = excluded.salle",
        (annee_id, jour, annee_id, rang, semaine, classe_id, nature, salle),
    )
    return code


def annuler_derniere_grille(annee_id: int) -> bool:
    """Return the grid as it was (EF-B12). False if there is nothing.

    *"A class deleted in the meantime does not come back to life: its
    cell is lost, the rest returns."* So the snapshot is re-read code by
    code, and unknown codes are SKIPPED — not recreated. Recreating a
    class deleted on purpose would be worse than losing its cell.
    """
    garde_ecriture(annee_id)
    lignes = query(
        "SELECT id, contenu FROM grilles_precedentes WHERE annee_id = ? "
        "ORDER BY id DESC LIMIT 1", (annee_id,))
    if not lignes:
        return False

    photo = json.loads(lignes[0]["contenu"])
    execute("DELETE FROM creneaux WHERE annee_id = ?", (annee_id,))
    vivantes = codes_de_lannee(annee_id)
    for case in photo:
        if case["code"] not in vivantes:
            continue
        execute(
            "INSERT INTO creneaux "
            "(annee_id, jour, horaire_id, semaine, classe_id, nature, salle) "
            "VALUES (?, ?, "
            " (SELECT id FROM horaires WHERE annee_id = ? AND rang = ?), "
            " ?, ?, ?, ?)",
            (annee_id, case["jour"], annee_id, case["rang"], case["semaine"],
             classe_id_de(annee_id, case["code"]), case["nature"],
             case["salle"]),
        )
    execute("DELETE FROM grilles_precedentes WHERE id = ?", (lignes[0]["id"],))
    return True


def poser_exception(annee_id: int, jour: str, rang: int, code: str) -> None:
    """An extra hour, or a CANCELLATION (EF-B11).

    An empty ``code`` = a cancellation. *"A calendar cell carries one
    decision only: setting the same cell again replaces"* — it is the
    schema's ``(annee, jour, horaire)`` uniqueness that holds it, not a
    test here.
    """
    garde_ecriture(annee_id)
    classe_id = classe_id_de(annee_id, code) if code else None
    execute(
        "INSERT INTO heures_exceptionnelles "
        "(annee_id, jour, horaire_id, classe_id, salle) VALUES (?, ?, "
        " (SELECT id FROM horaires WHERE annee_id = ? AND rang = ?), ?, '') "
        "ON CONFLICT (annee_id, jour, horaire_id) DO UPDATE SET "
        "classe_id = excluded.classe_id",
        (annee_id, jour, annee_id, rang, classe_id),
    )


def retirer_exception(annee_id: int, jour: str, rang: int) -> None:
    """Remove a cell's decision: the typical grid takes over again."""
    garde_ecriture(annee_id)
    execute(
        "DELETE FROM heures_exceptionnelles WHERE annee_id = ? AND jour = ? "
        "AND horaire_id = "
        "(SELECT id FROM horaires WHERE annee_id = ? AND rang = ?)",
        (annee_id, jour, annee_id, rang),
    )


def regler_horaire(annee_id: int, rang: int, debut: str, fin: str) -> None:
    """Set a slot's boundaries FOR THE WHOLE YEAR (EF-B3)."""
    garde_ecriture(annee_id)
    execute(
        "UPDATE horaires SET debut = ?, fin = ? WHERE annee_id = ? AND rang = ?",
        (debut, fin, annee_id, rang),
    )


def classe_id_de(annee_id: int, code: str) -> int | None:
    """A class's identifier by its code, or ``None``."""
    lignes = query(
        "SELECT id FROM classes WHERE annee_id = ? AND code = ?",
        (annee_id, code))
    return lignes[0]["id"] if lignes else None


feature = Feature(
    name="grille_data",
    kind="data",
    provides=[
        codes_de_lannee, lundi_affiche, semaine_affichee, creer_classe_vide,
        sauver_grille, poser_case, annuler_derniere_grille, poser_exception,
        retirer_exception, regler_horaire, classe_id_de,
    ],
    uses=["db", "annees"],
)
