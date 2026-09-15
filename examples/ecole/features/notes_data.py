"""features/notes_data — data : les évaluations, les notes, les refus.

``kind="data"``. Trois règles métier vivent ici parce qu'elles doivent
tenir **quel que soit l'écran** (RT-8), et pas parce que c'est pratique :

1. **une note supérieure au barème est refusée** (EF-D5), au plus bas
   niveau possible. L'écran l'explique ; c'est cette couche qui refuse ;
2. **la note globale d'une évaluation détaillée n'est jamais saisie**
   (EF-D4) : elle est la somme des sous-notes. Une saisie directe serait
   une seconde source de vérité pour la même valeur ;
3. **le barème d'une évaluation par compétences DEVIENT leur somme**
   (EF-D3), et le champ se verrouille à l'écran. Ici, il se recalcule.

EF-D8 — les corrections à reporter, et pourquoi c'est une TABLE
---------------------------------------------------------------
*« Une note changée après coup doit être reportée à la main sur École
Directe. La liste se constitue seule, survit à la fermeture, et ne
s'efface QUE lorsque le professeur dit l'avoir fait. »* Trois propriétés,
et chacune interdit une solution plus simple : « se constitue seule »
interdit un bouton, « survit à la fermeture » interdit un état de
session, « ne s'efface que sur ordre » interdit une purge par ancienneté.
"""

from __future__ import annotations

from datetime import date

from bretzel import Feature
from examples.ecole.core.db import execute, query, scalar
from examples.ecole.core.domain import competences_de
from examples.ecole.features.annees import garde_ecriture


class NoteRefuseeError(ValueError):
    """Une note dépasse son barème, ou une sous-note ses points (EF-D5).

    Une levée plutôt qu'un retour : l'écran doit EXPLIQUER le refus, donc
    il a besoin de la phrase, pas d'un booléen. Et une règle qu'on peut
    ignorer en oubliant de lire un retour ne tient pas « quel que soit
    l'écran ».
    """


def evaluations_de(classe_id: int, trimestre: int) -> list[dict]:
    """La liste d'EF-D1 : tout ce que la ligne doit dire, en une requête.

    ``saisies`` et ``effectif`` donnent l'avancement de la saisie — la
    seule colonne de cette liste qui ne soit pas une donnée mais un
    calcul, et celle qu'on regarde le soir pour savoir ce qui reste.
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
    """Les compétences d'une évaluation détaillée, avec leurs points."""
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
    """``eleve_id → {absent, valeur}`` — pour remplir la saisie."""
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
    """Les notes d'un élève sur un trimestre, pour sa fiche (EF-C3)."""
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
    """Ce qui reste à reporter à la main sur École Directe (EF-D8)."""
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
    """L'histogramme d'EF-D6 : quatre tranches sur le barème.

    Quatre et pas dix : à trente copies, dix tranches rendent un peigne
    illisible. Les bornes sont en QUARTS DE BARÈME et pas en notes sur
    vingt — un devoir sur 40 se lit avec les mêmes tranches qu'un devoir
    sur 10.
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
    """La moyenne des PRÉSENTS. Les absences ne comptent pas (§ 5.2)."""
    return scalar(
        "SELECT AVG(valeur) FROM notes WHERE evaluation_id = ? "
        "AND absent = 0 AND valeur IS NOT NULL", (evaluation_id,))


# ── Les écritures ────────────────────────────────────────────────────

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
    """Le même devoir dans plusieurs classes d'un niveau (EF-D2).

    *« Chacune garde la sienne, reliées entre elles. »* Le lien est
    ``commune_id``, et il vaut l'identifiant de la PREMIÈRE : la date peut
    différer d'une classe à l'autre, les moyennes se calculent par classe,
    et seule l'appartenance au même devoir est partagée.
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
    """Répartit des points sur les compétences — **et le barème SUIT**.

    EF-D3 : *« le barème devient leur somme et le champ se verrouille »*.
    Le verrouillage est à l'écran ; ici, le barème est simplement
    recalculé — si les deux divergeaient, une note valide selon l'un
    serait refusée par l'autre.
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
    """Une note, et le refus d'EF-D5 **au plus bas niveau possible**.

    Le refus est ici et pas dans l'écran parce qu'une règle métier tient
    quel que soit l'écran (RT-8) : l'import, un second formulaire, un
    script de reprise passeraient tous par cette porte.

    ⚠️ **Une note modifiée APRÈS coup entre dans la liste à reporter**
    (EF-D8), et c'est fait ici pour la même raison : la liste *« se
    constitue seule »*. Un appelant qui devrait y penser finirait par
    l'oublier — et l'oubli ne se voit qu'un mois plus tard, sur École
    Directe.
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

    # Une PREMIÈRE saisie n'est pas une correction : la liste ne doit
    # porter que ce qui a changé après avoir été reporté.
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
    """Une sous-note, refusée si elle dépasse les points de sa compétence."""
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
    # EF-D4 : **la note globale n'est jamais saisie** — elle est la somme
    # des sous-notes. La recalculer ici est ce qui garantit qu'il n'y a
    # jamais deux valeurs pour la même chose.
    execute(
        "UPDATE notes SET valeur = (SELECT COALESCE(SUM(valeur), 0) "
        "FROM sous_notes WHERE note_id = ?) WHERE id = ?",
        (note_id, note_id))


def marquer_reporte(evaluation_id: int, annee_id: int) -> None:
    """EF-D7 — avec la date du jour. *Savoir QUAND permet de comprendre
    une divergence entre les deux listes.*"""
    garde_ecriture(annee_id)
    execute("UPDATE evaluations SET reporte_le = ? WHERE id = ?",
            (date.today().isoformat(), evaluation_id))


def correction_faite(correction_id: int, annee_id: int) -> None:
    """EF-D8 — **la seule façon d'effacer une ligne de la liste**.

    Pas à l'ouverture, pas au bout de n jours : le professeur dit l'avoir
    fait, ou la ligne reste.
    """
    garde_ecriture(annee_id)
    execute("DELETE FROM corrections_a_reporter WHERE id = ?",
            (correction_id,))


def competences_proposees(cycle: str, type_evaluation: str) -> list[tuple]:
    """Ce que l'écran de répartition propose (EF-D3), cycle par cycle."""
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
