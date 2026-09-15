"""features/suivi_data — data : le travail à vérifier, et les deux rappels.

``kind="data"``. EF-H1 à EF-H4 et EF-I1 à EF-I5.

EF-H3 — **rien n'est effacé quand c'est fait**
-----------------------------------------------
*« Trois cahiers incomplets dans le trimestre disent quelque chose que
trois lignes effacées ne diraient plus. »* Une vérification faite reçoit
une DATE ; seule une ligne posée **par erreur** se supprime — *« la
cocher "fait" serait un mensonge »*.

Les deux rappels sont CALCULÉS, jamais tenus dans une liste
------------------------------------------------------------
*« Deux oublis que l'application voit venir, calculés à la demande et non
tenus dans une liste qui divergerait de la réalité. »* C'est pour ça
qu'aucune table ne les stocke : une liste de rappels se désynchronise du
jour où une note est saisie ailleurs, et personne ne le voit.

Et le décompte de séances porte QUATRE nuances, toutes payées :

- il se compte depuis l'**emploi du temps**, jour par jour, alternance
  comprise (RT-5) ;
- **vacances et fériés déduits** (RT-6, piège n° 3 : *seuil franchi deux
  semaines trop tôt*) ;
- sur le **trimestre en cours**, pas sur l'année (EF-I4, piège n° 4 :
  *juste au T1, faux aux T2 et T3*) ;
- **sans créneau, une classe n'est pas signalée** (EF-I3 : *mieux vaut se
  taire que signaler à tort*).
"""

from __future__ import annotations

from datetime import date, timedelta

from bretzel import Feature
from bretzel.state import AppState, field
from examples.ecole.core.db import execute, query
from examples.ecole.core.domain import est_jour_de_classe, semaine_ab
from examples.ecole.features.annees import garde_ecriture

#: EF-I1 — au bout de combien de jours une évaluation non reportée se
#: signale. *« Le compteur part de la PREMIÈRE note saisie, pas de la
#: dernière : corriger une note trois semaines après ne doit pas effacer
#: un rappel mérité. »*
JOURS_AVANT_RAPPEL = 15

#: EF-I2 — combien de fois une classe doit avoir été vue avant qu'on
#: signale les élèves sans observation.
SEANCES_AVANT_RAPPEL = 5

#: EF-I5 — au-delà de combien d'élèves on donne le NOMBRE et un lien
#: plutôt que la liste. *« En début de trimestre toute la classe est sans
#: observation, et la liste noierait les quelques oubliés qu'on
#: cherche. »*
NOMS_AFFICHES = 8


class SuiviRev(AppState):
    """Le jeton des zones de suivi. Même raison que les autres."""

    rev: int = field(default=0, merge="add")


def verifications_de(classe_id: int, en_attente: bool = True) -> list[dict]:
    """Le travail à vérifier d'une classe (EF-H1).

    *« La classe est gardée à côté, parce que c'est par classe qu'on relit
    la liste — et qu'un élève peut changer de classe en cours d'année. »*
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
    """Celles d'un élève — **elles le SUIVENT** (EF-H1).

    Le rappel porte sur un élève nommé, pas sur un texte libre : il reste
    attaché à lui même s'il change de classe.
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
    """EF-H2 — *« une note qui demande dix secondes de plus est une note
    qu'on ne prend pas »*."""
    garde_ecriture(annee_id)
    execute(
        "INSERT INTO verifications (eleve_id, classe_id, motif, cree_le, "
        "fait_le) VALUES (?, ?, ?, ?, NULL)",
        (eleve_id, classe_id, motif.strip()[:80], date.today().isoformat()))
    SuiviRev().rev += 1


def marquer_faite(verification_id: int, annee_id: int) -> None:
    """EF-H3 — la date est POSÉE, la ligne reste."""
    garde_ecriture(annee_id)
    execute("UPDATE verifications SET fait_le = ? WHERE id = ?",
            (date.today().isoformat(), verification_id))
    SuiviRev().rev += 1


def supprimer_verification(verification_id: int, annee_id: int) -> None:
    """La ligne posée PAR ERREUR — *« la cocher "fait" serait un
    mensonge »*."""
    garde_ecriture(annee_id)
    execute("DELETE FROM verifications WHERE id = ?", (verification_id,))
    SuiviRev().rev += 1


# ── Les deux rappels, calculés à la demande ──────────────────────────

def seances_faites(annee: dict, classe_id: int, depuis: date,
                   jusqua: date) -> int:
    """Combien de fois cette classe a été vue entre deux dates.

    **Le décompte d'EF-I2, avec ses trois nuances.** Il parcourt les
    jours un par un : c'est le seul moyen de déduire vacances et fériés
    (RT-6) tout en respectant l'alternance (RT-5). Une multiplication
    « semaines × créneaux » serait plus rapide et fausse des deux côtés.
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
    """EF-I3 — *« sans créneau, une classe n'est pas signalée »*."""
    return bool(query(
        "SELECT 1 FROM creneaux WHERE annee_id = ? AND classe_id = ? LIMIT 1",
        (annee_id, classe_id)))


def notes_non_reportees(annee_id: int) -> list[dict]:
    """EF-I1 — les évaluations dont la PREMIÈRE note date de plus de 15 jours.

    ⚠️ **``MIN(...)`` et pas ``MAX(...)``**, et c'est l'exigence :
    *« le compteur part de la première note saisie, pas de la dernière :
    corriger une note trois semaines après ne doit pas effacer un rappel
    mérité »*. Faute de date sur la note elle-même, c'est la date de
    l'ÉVALUATION qui fait office — elle est antérieure à toute saisie,
    donc le rappel arrive au plus tôt, jamais au plus tard.
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
    """EF-I2 — les classes vues au moins cinq fois dont des élèves n'ont
    aucun critère coché.

    Le décompte porte sur le **trimestre en cours** (EF-I4, piège n° 4) :
    *« partir de la rentrée était juste au premier trimestre et faux aux
    deux suivants — une classe franchissait le seuil dès le premier jour,
    et l'application signalait alors toute la classe »*.
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
    """Ce qui a été vu la dernière fois, pour EF-B15.

    *« Le numéro et le titre de la SÉANCE, rien d'autre — ni la date, ni
    le chapitre, ni le travail donné. Le chapitre est le même pendant six
    semaines et ne situe pas la classe ; il ne sert que de secours pour
    une heure notée sans séance choisie. »*
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
