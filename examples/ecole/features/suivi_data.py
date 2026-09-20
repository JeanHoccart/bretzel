"""features/suivi_data — data: the work to check, and the two reminders.

``kind="data"``. EF-H1 to EF-H4 and EF-I1 to EF-I5.

EF-H3 — **nothing is erased when it is done**
----------------------------------------------
*"Three incomplete exercise books in the term say something that three
erased rows would no longer say."* A check done receives a DATE; only a
row set **by mistake** is deleted — *"ticking it 'done' would be a lie"*.

The two reminders are COMPUTED, never kept in a list
------------------------------------------------------
*"Two oversights the application sees coming, computed on demand and not
kept in a list that would diverge from reality."* That is why no table
stores them: a list of reminders goes out of sync the day a mark is
entered elsewhere, and nobody sees it.

And the session count carries FOUR nuances, all paid for:

- it counts from the **timetable**, day by day, alternation included
  (RT-5);
- **holidays and public holidays deducted** (RT-6, trap no. 3:
  *threshold crossed two weeks too early*);
- over the **current term**, not the year (EF-I4, trap no. 4: *right in
  T1, wrong in T2 and T3*);
- **with no slot, a class is not flagged** (EF-I3: *better to keep quiet
  than flag wrongly*).
"""

from __future__ import annotations

from datetime import date, timedelta

from bretzel import Feature
from bretzel.state import AppState, field
from examples.ecole.core.db import execute, query
from examples.ecole.core.domain import est_jour_de_classe, semaine_ab
from examples.ecole.features.annees import garde_ecriture

#: EF-I1 — after how many days an unreported assessment flags itself.
#: *"The counter starts from the FIRST mark entered, not from the last:
#: correcting a mark three weeks later must not erase a deserved
#: reminder."*
JOURS_AVANT_RAPPEL = 15

#: EF-I2 — how many times a class must have been seen before the pupils
#: with no observation are flagged.
SEANCES_AVANT_RAPPEL = 5

#: EF-I5 — beyond how many pupils we give the NUMBER and a link rather
#: than the list. *"At the start of term the whole class has no
#: observation, and the list would drown the few forgotten ones one is
#: looking for."*
NOMS_AFFICHES = 8


class SuiviRev(AppState):
    """The follow-up zones' token. The same reason as the others."""

    rev: int = field(default=0, merge="add")


def verifications_de(classe_id: int, en_attente: bool = True) -> list[dict]:
    """A class's work to check (EF-H1).

    *"The class is kept beside it, because it is by class that the list
    is re-read — and because a pupil may change class mid-year."*
    """
    clause = ("v.fait_le IS NULL" if en_attente
              else "v.fait_le IS NOT NULL")
    return query(
        f"""
        SELECT v.id, v.motif, v.cree_le, v.fait_le, v.eleve_id,
               e.nom, e.prenom
        FROM verifications v JOIN eleves e ON e.id = v.eleve_id
        WHERE v.classe_id = ? AND {clause}
        ORDER BY v.cree_le DESC
        """,
        (classe_id,),
    )


def verifications_eleve(eleve_id: int) -> list[dict]:
    """A pupil's own — **they FOLLOW them** (EF-H1).

    The reminder is about a named pupil, not free text: it stays attached
    to them even if they change class.
    """
    return query(
        """
        SELECT v.id, v.motif, v.cree_le, v.fait_le, c.code
        FROM verifications v JOIN classes c ON c.id = v.classe_id
        WHERE v.eleve_id = ? ORDER BY v.cree_le DESC
        """,
        (eleve_id,),
    )


def poser_verification(eleve_id: int, classe_id: int, annee_id: int,
                       motif: str) -> None:
    """EF-H2 — *"a note that takes ten seconds longer is a note one does
    not take"*."""
    garde_ecriture(annee_id)
    execute(
        "INSERT INTO verifications (eleve_id, classe_id, motif, cree_le, "
        "fait_le) VALUES (?, ?, ?, ?, NULL)",
        (eleve_id, classe_id, motif.strip()[:80], date.today().isoformat()))
    SuiviRev().rev += 1


def marquer_faite(verification_id: int, annee_id: int) -> None:
    """EF-H3 — the date is SET, the row stays."""
    garde_ecriture(annee_id)
    execute("UPDATE verifications SET fait_le = ? WHERE id = ?",
            (date.today().isoformat(), verification_id))
    SuiviRev().rev += 1


def supprimer_verification(verification_id: int, annee_id: int) -> None:
    """The row set BY MISTAKE — *"ticking it 'done' would be a lie"*."""
    garde_ecriture(annee_id)
    execute("DELETE FROM verifications WHERE id = ?", (verification_id,))
    SuiviRev().rev += 1


# ── The two reminders, computed on demand ────────────────────────────

def seances_faites(annee: dict, classe_id: int, depuis: date,
                   jusqua: date) -> int:
    """How many times this class was seen between two dates.

    **EF-I2's count, with its three nuances.** It walks the days one by
    one: it is the only way of deducting holidays and public holidays
    (RT-6) while respecting the alternation (RT-5). A "weeks × slots"
    multiplication would be faster and wrong on both counts.
    """
    if not annee["lundi_ref"]:
        return 0
    lundi_ref = date.fromisoformat(annee["lundi_ref"])
    periodes = [
        (r["libelle"], date.fromisoformat(r["debut"]),
         date.fromisoformat(r["fin"]))
        for r in query("SELECT libelle, debut, fin FROM vacances "
                       "WHERE annee_id = ?", (annee["id"],))
    ]
    grille: dict[tuple[int, str], int] = {}
    for ligne in query(
        "SELECT jour, semaine, COUNT(*) AS n FROM creneaux "
        "WHERE annee_id = ? AND classe_id = ? AND nature = '' "
        "GROUP BY jour, semaine",
        (annee["id"], classe_id),
    ):
        grille[(ligne["jour"], ligne["semaine"])] = ligne["n"]
    if not grille:
        return 0

    total = 0
    jour = depuis
    while jour <= jusqua:
        if est_jour_de_classe(jour, periodes):
            total += grille.get((jour.weekday(),
                                 semaine_ab(jour, lundi_ref)), 0)
        jour += timedelta(days=1)
    return total


def a_des_creneaux(annee_id: int, classe_id: int) -> bool:
    """EF-I3 — *"with no slot, a class is not flagged"*."""
    return bool(query(
        "SELECT 1 FROM creneaux WHERE annee_id = ? AND classe_id = ? LIMIT 1",
        (annee_id, classe_id)))


def notes_non_reportees(annee_id: int) -> list[dict]:
    """EF-I1 — the assessments whose FIRST mark is more than 15 days old.

    ⚠️ **``MIN(...)`` and not ``MAX(...)``**, and it is the requirement:
    *"the counter starts from the first mark entered, not from the last:
    correcting a mark three weeks later must not erase a deserved
    reminder"*. For want of a date on the mark itself, it is the
    ASSESSMENT's date that stands in — it precedes any entry, so the
    reminder arrives at the earliest, never at the latest.
    """
    limite = (date.today() - timedelta(days=JOURS_AVANT_RAPPEL)).isoformat()
    return query(
        """
        SELECT ev.id, ev.nom, ev.date, c.id AS classe_id, c.code,
               COUNT(n.id) AS saisies
        FROM evaluations ev
        JOIN classes c ON c.id = ev.classe_id
        JOIN notes n ON n.evaluation_id = ev.id
        WHERE c.annee_id = ? AND ev.reporte_le IS NULL AND ev.date <= ?
        GROUP BY ev.id ORDER BY ev.date
        """,
        (annee_id, limite),
    )


def eleves_sans_observation(annee: dict, trimestre: int,
                            debut_trimestre: date) -> list[dict]:
    """EF-I2 — the classes seen at least five times where some pupils
    have no criterion ticked.

    The count covers the **current term** (EF-I4, trap no. 4): *"starting
    from the beginning of the school year was right in the first term and
    wrong in the next two — a class crossed the threshold on the very
    first day, and the application then flagged the whole class"*.
    """
    signales: list[dict] = []
    for classe in query(
        "SELECT id, code FROM classes WHERE annee_id = ? ORDER BY rang",
        (annee["id"],),
    ):
        if not a_des_creneaux(annee["id"], classe["id"]):
            continue          # EF-I3 : mieux vaut se taire.
        vues = seances_faites(annee, classe["id"], debut_trimestre,
                              date.today())
        if vues < SEANCES_AVANT_RAPPEL:
            continue
        oublies = query(
            """
            SELECT e.id, e.nom, e.prenom
            FROM inscriptions i JOIN eleves e ON e.id = i.eleve_id
            WHERE i.classe_id = ? AND i.fin IS NULL
              AND NOT EXISTS (
                  SELECT 1 FROM fiches f JOIN fiches_niveaux fn
                       ON fn.fiche_id = f.id
                   WHERE f.eleve_id = e.id AND f.classe_id = i.classe_id
                     AND f.trimestre = ?)
            ORDER BY e.nom COLLATE NOCASE
            """,
            (classe["id"], trimestre),
        )
        if oublies:
            signales.append({"classe_id": classe["id"],
                             "code": classe["code"], "vues": vues,
                             "eleves": oublies})
    return signales


def derniere_seance(classe_id: int) -> dict | None:
    """What was covered last time, for EF-B15.

    *"The SESSION's number and title, nothing else — neither the date,
    nor the chapter, nor the homework set. The chapter is the same for
    six weeks and does not situate the class; it only serves as a
    fallback for an hour recorded with no session chosen."*
    """
    lignes = query(
        """
        SELECT ca.seance_numero, ca.seance_titre, ca.date, ch.titre AS chapitre
        FROM cahier ca LEFT JOIN chapitres ch ON ch.id = ca.chapitre_id
        WHERE ca.classe_id = ? ORDER BY ca.date DESC, ca.id DESC LIMIT 1
        """,
        (classe_id,),
    )
    return lignes[0] if lignes else None


feature = Feature(
    name="suivi_data",
    kind="data",
    provides=[
        SuiviRev, verifications_de, verifications_eleve, poser_verification,
        marquer_faite, supprimer_verification, seances_faites,
        a_des_creneaux, notes_non_reportees, eleves_sans_observation,
        derniere_seance,
    ],
    uses=["db", "annees"],
)
