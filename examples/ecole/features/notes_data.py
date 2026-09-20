"""features/notes_data — data: the assessments, the marks, the refusals.

``kind="data"``. Three business rules live here because they must hold
**whatever the screen** (RT-8), and not because it is convenient:

1. **a mark above the scale is refused** (EF-D5), at the lowest possible
   level. The screen explains it; it is this layer that refuses;
2. **a detailed assessment's overall mark is never entered** (EF-D4): it
   is the sum of the sub-marks. A direct entry would be a second source
   of truth for the same value;
3. **a by-skill assessment's scale BECOMES their sum** (EF-D3), and the
   field locks on screen. Here, it is recomputed.

EF-D8 — the corrections to report, and why it is a TABLE
---------------------------------------------------------
*"A mark changed after the fact must be reported by hand on École
Directe. The list builds itself, survives closing, and is only cleared
WHEN the teacher says they have done it."* Three properties, and each one
forbids a simpler solution: "builds itself" forbids a button, "survives
closing" forbids a session state, "only cleared on order" forbids a purge
by age.
"""

from __future__ import annotations

from datetime import date

from bretzel import Feature
from examples.ecole.core.db import execute, query, scalar
from examples.ecole.core.domain import competences_de
from examples.ecole.features.annees import garde_ecriture


class NoteRefuseeError(ValueError):
    """A mark exceeds its scale, or a sub-mark its points (EF-D5).

    A raise rather than a return: the screen must EXPLAIN the refusal, so
    it needs the sentence, not a boolean. And a rule one can ignore by
    forgetting to read a return does not hold "whatever the screen".
    """


def evaluations_de(classe_id: int, trimestre: int) -> list[dict]:
    """EF-D1's list: everything the row must say, in one query.

    ``saisies`` and ``effectif`` give the entry's progress — the only
    column of this list that is not data but a computation, and the one
    looked at in the evening to know what is left.
    """
    return query(
        """
        SELECT ev.id, ev.nom, ev.type, ev.date, ev.bareme, ev.coefficient,
               ev.reporte_le, ev.commune_id,
               (SELECT COUNT(*) FROM notes n WHERE n.evaluation_id = ev.id)
                   AS saisies,
               (SELECT COUNT(*) FROM inscriptions i
                 WHERE i.classe_id = ev.classe_id AND i.fin IS NULL)
                   AS effectif,
               (SELECT COUNT(*) FROM competences_evaluees ce
                 WHERE ce.evaluation_id = ev.id) AS competences
        FROM evaluations ev
        WHERE ev.classe_id = ? AND ev.trimestre = ?
        ORDER BY ev.date DESC, ev.id DESC
        """,
        (classe_id, trimestre),
    )


def evaluation(evaluation_id: int) -> dict | None:
    lignes = query(
        """
        SELECT ev.id, ev.classe_id, ev.trimestre, ev.nom, ev.type, ev.date,
               ev.bareme, ev.coefficient, ev.reporte_le, ev.commune_id,
               c.code, c.cycle, c.annee_id
        FROM evaluations ev JOIN classes c ON c.id = ev.classe_id
        WHERE ev.id = ?
        """,
        (evaluation_id,),
    )
    return lignes[0] if lignes else None


def competences_evaluees_de(evaluation_id: int) -> list[dict]:
    """A detailed assessment's skills, with their points."""
    return query(
        """
        SELECT ce.id, ce.points, ce.sous_competence, c.code, c.libelle
        FROM competences_evaluees ce
        JOIN competences c ON c.id = ce.competence_id
        WHERE ce.evaluation_id = ? ORDER BY c.rang
        """,
        (evaluation_id,),
    )


def notes_de(evaluation_id: int) -> dict[int, dict]:
    """``eleve_id → {absent, valeur}`` — to fill the entry form."""
    return {
        r["eleve_id"]: {"absent": bool(r["absent"]), "valeur": r["valeur"]}
        for r in query(
            "SELECT eleve_id, absent, valeur FROM notes WHERE evaluation_id = ?",
            (evaluation_id,))
    }


def sous_notes_de(evaluation_id: int) -> dict[tuple[int, int], float]:
    """``(eleve_id, competence_evaluee_id) → valeur``."""
    return {
        (r["eleve_id"], r["competence_evaluee_id"]): r["valeur"]
        for r in query(
            """
            SELECT n.eleve_id, sn.competence_evaluee_id, sn.valeur
            FROM sous_notes sn JOIN notes n ON n.id = sn.note_id
            WHERE n.evaluation_id = ?
            """,
            (evaluation_id,))
    }


def notes_du_trimestre(eleve_id: int, classe_id: int,
                       trimestre: int) -> list[dict]:
    """A pupil's marks over a term, for their sheet (EF-C3)."""
    return query(
        """
        SELECT ev.id, ev.nom, ev.type, ev.date, ev.bareme, ev.coefficient,
               n.absent, n.valeur
        FROM evaluations ev
        LEFT JOIN notes n ON n.evaluation_id = ev.id AND n.eleve_id = ?
        WHERE ev.classe_id = ? AND ev.trimestre = ?
        ORDER BY ev.date
        """,
        (eleve_id, classe_id, trimestre),
    )


def corrections_en_attente(annee_id: int) -> list[dict]:
    """What is left to report by hand on École Directe (EF-D8)."""
    return query(
        """
        SELECT co.id, co.ancienne, co.nouvelle, co.cree_le,
               e.nom, e.prenom, ev.nom AS evaluation, c.code
        FROM corrections_a_reporter co
        JOIN evaluations ev ON ev.id = co.evaluation_id
        JOIN classes c ON c.id = ev.classe_id
        JOIN eleves e ON e.id = co.eleve_id
        WHERE c.annee_id = ?
        ORDER BY co.cree_le DESC
        """,
        (annee_id,),
    )


def repartition(evaluation_id: int, bareme: float) -> list[dict]:
    """EF-D6's histogram: four bands over the scale.

    Four and not ten: at thirty papers, ten bands make an unreadable
    comb. The bounds are in QUARTERS OF THE SCALE and not in marks out of
    twenty — a test out of 40 reads with the same bands as a test out of
    10.
    """
    valeurs = [
        r["valeur"] for r in query(
            "SELECT valeur FROM notes WHERE evaluation_id = ? AND absent = 0 "
            "AND valeur IS NOT NULL", (evaluation_id,))
    ]
    if not bareme:
        return []
    tranches = [(0, 0.25), (0.25, 0.5), (0.5, 0.75), (0.75, 1.01)]
    resultat = []
    for bas, haut in tranches:
        compte = sum(1 for v in valeurs
                     if bas * bareme <= v < haut * bareme)
        resultat.append({
            "label": f"{bas * bareme:.0f}–{min(haut, 1.0) * bareme:.0f}",
            "value": compte,
        })
    return resultat


def moyenne_de_classe(evaluation_id: int) -> float | None:
    """The average of those PRESENT. Absences do not count (§ 5.2)."""
    return scalar(
        "SELECT AVG(valeur) FROM notes WHERE evaluation_id = ? "
        "AND absent = 0 AND valeur IS NOT NULL", (evaluation_id,))


# ── The writes ───────────────────────────────────────────────────────

def creer_evaluation(classe_id: int, annee_id: int, champs: dict) -> int:
    garde_ecriture(annee_id)
    return execute(
        "INSERT INTO evaluations (classe_id, trimestre, nom, type, date, "
        "bareme, coefficient, reporte_le, commune_id) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, NULL, ?)",
        (classe_id, champs["trimestre"], champs["nom"], champs["type"],
         champs["date"], champs["bareme"], champs["coefficient"],
         champs.get("commune_id")),
    )


def donner_a_plusieurs(classes: list[int], annee_id: int,
                       champs: dict) -> list[int]:
    """The same test in several classes of a level (EF-D2).

    *"Each keeps its own, linked to each other."* The link is
    ``commune_id``, and it is the identifier of the FIRST: the date may
    differ from one class to another, the averages are computed per
    class, and only belonging to the same test is shared.
    """
    garde_ecriture(annee_id)
    identifiants: list[int] = []
    for classe_id in classes:
        eval_id = creer_evaluation(classe_id, annee_id, champs)
        if not identifiants:
            execute("UPDATE evaluations SET commune_id = ? WHERE id = ?",
                    (eval_id, eval_id))
            champs = {**champs, "commune_id": eval_id}
        identifiants.append(eval_id)
    return identifiants


def poser_competences(evaluation_id: int, annee_id: int,
                      points: dict[str, float], cycle: str) -> float:
    """Distribute points over the skills — **and the scale FOLLOWS**.

    EF-D3: *"the scale becomes their sum and the field locks"*. The
    locking is on screen; here, the scale is simply recomputed — if the
    two diverged, a mark valid according to one would be refused by the
    other.
    """
    garde_ecriture(annee_id)
    execute("DELETE FROM competences_evaluees WHERE evaluation_id = ?",
            (evaluation_id,))
    total = 0.0
    for code, valeur in points.items():
        if not valeur:
            continue
        ligne = query(
            "SELECT id FROM competences WHERE cycle = ? AND code = ?",
            (cycle, code))
        if not ligne:
            continue
        execute(
            "INSERT INTO competences_evaluees "
            "(evaluation_id, competence_id, points, sous_competence) "
            "VALUES (?, ?, ?, '')",
            (evaluation_id, ligne[0]["id"], float(valeur)))
        total += float(valeur)
    if total:
        execute("UPDATE evaluations SET bareme = ? WHERE id = ?",
                (total, evaluation_id))
    return total


def poser_note(evaluation_id: int, eleve_id: int, annee_id: int,
               absent: bool, valeur: float | None, bareme: float) -> None:
    """A mark, and EF-D5's refusal **at the lowest possible level**.

    The refusal is here and not in the screen because a business rule
    holds whatever the screen (RT-8): the import, a second form, a
    recovery script would all go through this door.

    ⚠️ **A mark modified AFTER the fact enters the list to report**
    (EF-D8), and it is done here for the same reason: the list *"builds
    itself"*. A caller that had to think of it would end up forgetting —
    and the oversight only shows a month later, on École Directe.
    """
    garde_ecriture(annee_id)
    if not absent and valeur is not None and valeur > bareme:
        raise NoteRefuseeError(
            f"{valeur:g} dépasse le barème de {bareme:g}. Une note ne peut "
            f"pas valoir plus que ce qui était à gagner."
        )
    if not absent and valeur is not None and valeur < 0:
        raise NoteRefuseeError("Une note négative n'existe pas.")

    ancienne = query(
        "SELECT valeur FROM notes WHERE evaluation_id = ? AND eleve_id = ?",
        (evaluation_id, eleve_id))
    deja = ancienne[0]["valeur"] if ancienne else None

    execute(
        "INSERT INTO notes (evaluation_id, eleve_id, absent, valeur) "
        "VALUES (?, ?, ?, ?) "
        "ON CONFLICT (evaluation_id, eleve_id) DO UPDATE SET "
        "absent = excluded.absent, valeur = excluded.valeur",
        (evaluation_id, eleve_id, int(absent),
         None if absent else valeur),
    )

    # A FIRST entry is not a correction: the list must carry only what
    # changed after having been reported.
    if ancienne and deja is not None and not absent and valeur != deja:
        execute(
            "INSERT INTO corrections_a_reporter "
            "(evaluation_id, eleve_id, ancienne, nouvelle, cree_le) "
            "VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT (evaluation_id, eleve_id) DO UPDATE SET "
            "nouvelle = excluded.nouvelle, cree_le = excluded.cree_le",
            (evaluation_id, eleve_id, deja, valeur,
             date.today().isoformat()),
        )


def poser_sous_note(evaluation_id: int, eleve_id: int, annee_id: int,
                    competence_evaluee_id: int, valeur: float,
                    points: float) -> None:
    """A sub-mark, refused if it exceeds its skill's points."""
    garde_ecriture(annee_id)
    if valeur > points:
        raise NoteRefuseeError(
            f"{valeur:g} dépasse les {points:g} points de cette compétence."
        )
    lignes = query(
        "SELECT id FROM notes WHERE evaluation_id = ? AND eleve_id = ?",
        (evaluation_id, eleve_id))
    if not lignes:
        note_id = execute(
            "INSERT INTO notes (evaluation_id, eleve_id, absent, valeur) "
            "VALUES (?, ?, 0, 0)", (evaluation_id, eleve_id))
    else:
        note_id = lignes[0]["id"]
    execute(
        "INSERT INTO sous_notes (note_id, competence_evaluee_id, valeur) "
        "VALUES (?, ?, ?) "
        "ON CONFLICT (note_id, competence_evaluee_id) DO UPDATE SET "
        "valeur = excluded.valeur",
        (note_id, competence_evaluee_id, valeur))
    # EF-D4: **the overall mark is never entered** — it is the sum of
    # the sub-marks. Recomputing it here is what guarantees there are
    # never two values for the same thing.
    execute(
        "UPDATE notes SET valeur = (SELECT COALESCE(SUM(valeur), 0) "
        "FROM sous_notes WHERE note_id = ?) WHERE id = ?",
        (note_id, note_id))


def marquer_reporte(evaluation_id: int, annee_id: int) -> None:
    """EF-D7 — with today's date. *Knowing WHEN makes a divergence
    between the two lists understandable.*"""
    garde_ecriture(annee_id)
    execute("UPDATE evaluations SET reporte_le = ? WHERE id = ?",
            (date.today().isoformat(), evaluation_id))


def correction_faite(correction_id: int, annee_id: int) -> None:
    """EF-D8 — **the only way of clearing a row from the list**.

    Not on opening, not after n days: the teacher says they have done it,
    or the row stays.
    """
    garde_ecriture(annee_id)
    execute("DELETE FROM corrections_a_reporter WHERE id = ?",
            (correction_id,))


def competences_proposees(cycle: str, type_evaluation: str) -> list[tuple]:
    """What the distribution screen proposes (EF-D3), cycle by cycle."""
    return list(competences_de(cycle, type_evaluation))


feature = Feature(
    name="notes_data",
    kind="data",
    provides=[
        NoteRefuseeError, evaluations_de, evaluation, competences_evaluees_de,
        notes_de, sous_notes_de, notes_du_trimestre, corrections_en_attente,
        repartition, moyenne_de_classe, creer_evaluation, donner_a_plusieurs,
        poser_competences, poser_note, poser_sous_note, marquer_reporte,
        correction_faite, competences_proposees,
    ],
    uses=["db", "annees"],
)
