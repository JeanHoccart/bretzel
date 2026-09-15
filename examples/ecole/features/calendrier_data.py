"""features/calendrier_data — data : l'année, ses trimestres, ses périodes.

``kind="data"`` : aucune page. Elle porte les lectures du calendrier et
**les six écritures gardées par RT-1** — chacune commence par
:func:`~examples.ecole.features.annees.garde_ecriture`, et c'est la seule
raison pour laquelle une page peut se contenter de ne pas afficher un
bouton (EF-C10) : le refus existe en dessous.

Ce qu'elle calcule et que personne d'autre ne doit recalculer
-------------------------------------------------------------
:func:`cours_perdus` est la réponse d'EF-A11, et elle a **trois formes
distinctes** qu'il ne faut surtout pas confondre :

==================  ===================================================
ce qu'elle rend     ce que ça veut dire
==================  ===================================================
``None``            l'alternance est indéterminée — pas de date de
                    référence de semaine A. On ne rend **pas**
                    « aucun cours » : on ne sait pas (RT-4)
``[]``              la liste est VIDE, et c'est la bonne nouvelle :
                    ce jour-là il n'y avait aucun cours à perdre
``[(code, n), …]``  ce que ça coûte, la classe la plus touchée d'abord
==================  ===================================================
"""

from __future__ import annotations

from collections import Counter
from datetime import date, timedelta

from bretzel import Feature
from examples.ecole.core.db import execute, query
from examples.ecole.core.domain import semaine_ab
from examples.ecole.features.annees import garde_ecriture


def horaires_de(annee_id: int) -> list[dict]:
    """Les huit bornes de la journée, dans l'ordre (EF-B3)."""
    return query(
        "SELECT id, rang, debut, fin FROM horaires "
        "WHERE annee_id = ? ORDER BY rang",
        (annee_id,),
    )


def trimestres_de(annee_id: int) -> dict[tuple[str, int], str]:
    """``(cycle, numéro) → fin``, et rien pour les cases vides.

    Un dict plutôt qu'une liste : l'écran demande six cases nommées
    (EF-A3), et une case absente doit se lire comme absente — pas comme
    une ligne à trouver dans une liste.
    """
    return {
        (r["cycle"], r["numero"]): r["fin"] or ""
        for r in query(
            "SELECT cycle, numero, fin FROM trimestres WHERE annee_id = ?",
            (annee_id,),
        )
    }


def periodes_de(annee_id: int) -> list[dict]:
    """Les périodes sans classe, **dans l'ordre de l'année** (EF-A6).

    *« L'ordre par catégorie — les quatre vacances d'abord — mettait la
    journée pédagogique du 16 octobre sous Pâques »* : c'est le piège
    n° 13, et il se ferme ici, dans le ``ORDER BY``, pas dans l'écran.
    """
    return query(
        "SELECT id, libelle, debut, fin FROM vacances "
        "WHERE annee_id = ? ORDER BY debut, fin",
        (annee_id,),
    )


def cours_perdus(
    annee: dict, debut: date, fin: date
) -> list[tuple[str, int]] | None:
    """Ce qu'une période fait perdre comme heures (EF-A11).

    ⚠️ **Passe par :func:`~examples.ecole.core.domain.semaine_ab`, jamais
    par un numéro de semaine.** C'est le piège n° 2 : compté sur les
    numéros ISO, le décompte attribue les heures à la mauvaise semaine
    dès janvier, une année sur cinq. Le seul endroit où l'alternance se
    calcule dans l'app est cette fonction de domaine.

    Le dimanche est sauté ; le samedi non, la grille va jusque-là.
    """
    if not annee["lundi_ref"]:
        return None
    lundi_ref = date.fromisoformat(annee["lundi_ref"])

    grille: dict[tuple[int, str], list[str]] = {}
    for ligne in query(
        "SELECT c.code, cr.jour, cr.semaine FROM creneaux cr "
        "JOIN classes c ON c.id = cr.classe_id WHERE cr.annee_id = ?",
        (annee["id"],),
    ):
        grille.setdefault((ligne["jour"], ligne["semaine"]), []).append(
            ligne["code"])

    compte: Counter[str] = Counter()
    jour = debut
    while jour <= fin:
        if jour.weekday() != 6:
            for code in grille.get(
                    (jour.weekday(), semaine_ab(jour, lundi_ref)), ()):
                compte[code] += 1
        jour += timedelta(days=1)
    # La plus touchée d'abord, puis le code — sans le second critère,
    # deux classes à égalité changeraient de place d'un rendu à l'autre.
    return sorted(compte.items(), key=lambda paire: (-paire[1], paire[0]))


# ── Les écritures. Chacune s'ouvre sur la garde RT-1 ──────────────────

def modifier_annee(annee_id: int, champs: dict[str, str]) -> None:
    """Corrige le libellé, le début, la fin, la référence (EF-A1)."""
    garde_ecriture(annee_id)
    execute(
        "UPDATE annees SET libelle = ?, debut = ?, fin = ?, lundi_ref = ? "
        "WHERE id = ?",
        (champs["libelle"], champs["debut"], champs["fin"],
         champs["lundi_ref"] or None, annee_id),
    )


def creer_annee(libelle: str, debut: str, fin: str) -> int:
    """Crée une année nouvelle, **en consultation** (EF-A2).

    Pas de garde RT-1 ici, et ce n'est pas un oubli : créer une année
    n'écrit dans aucune. La nouvelle naît hors service — c'est
    :func:`designer_en_cours` qui la met en service, et c'est un second
    geste exprès. Une année qui deviendrait « en cours » à sa création
    ferait basculer tous les écrans sur une base vide.
    """
    return execute(
        "INSERT INTO annees (libelle, debut, fin, en_cours, lundi_ref) "
        "VALUES (?, ?, ?, 0, NULL)",
        (libelle, debut, fin),
    )


def designer_en_cours(annee_id: int) -> None:
    """Bascule l'année en service. **Une seule à la fois** (§ 5.1).

    Pas de garde RT-1 : c'est l'opération qui DÉPLACE la barrière, elle
    ne peut pas être derrière elle. Les deux écritures sont faites dans
    cet ordre — on éteint avant d'allumer — pour qu'aucun instant
    intermédiaire n'ait deux années en cours.
    """
    execute("UPDATE annees SET en_cours = 0 WHERE en_cours = 1")
    execute("UPDATE annees SET en_cours = 1 WHERE id = ?", (annee_id,))


def poser_trimestre(annee_id: int, cycle: str, numero: int, fin: str) -> None:
    """Pose (ou efface) la FIN d'un trimestre (EF-A3).

    Le début n'est jamais saisi : il se lit comme le lendemain du
    précédent. Une fin vide efface la ligne plutôt que d'écrire une
    chaîne vide — une case vide doit se lire comme vide partout, y
    compris dans la base.
    """
    garde_ecriture(annee_id)
    if not fin:
        execute(
            "DELETE FROM trimestres WHERE annee_id = ? AND cycle = ? "
            "AND numero = ?",
            (annee_id, cycle, numero),
        )
        return
    execute(
        "INSERT INTO trimestres (annee_id, cycle, numero, fin) "
        "VALUES (?, ?, ?, ?) "
        "ON CONFLICT (annee_id, cycle, numero) DO UPDATE SET fin = excluded.fin",
        (annee_id, cycle, numero, fin),
    )


def poser_periode(annee_id: int, libelle: str, debut: str, fin: str) -> None:
    """Pose, corrige ou EFFACE une période sans classe (EF-A5).

    Les trois règles du cahier, dans l'ordre où elles se lisent :

    - un **début vide efface** la période. C'est la façon de retirer une
      ligne sans un bouton de plus, et c'est celle que le professeur
      connaît ;
    - une **fin vide vaut le début** : un jour férié se saisit d'une
      seule date, et il ressort avec ses deux dates identiques (EF-A8) ;
    - le nom fait la clé, parce que les quatre vacances de zone B sont
      PROPOSÉES et se remplissent par leur nom (EF-A4).
    """
    garde_ecriture(annee_id)
    if not debut:
        execute("DELETE FROM vacances WHERE annee_id = ? AND libelle = ?",
                (annee_id, libelle))
        return
    execute(
        "INSERT INTO vacances (annee_id, libelle, debut, fin) "
        "VALUES (?, ?, ?, ?) "
        "ON CONFLICT (annee_id, libelle) DO UPDATE SET "
        "debut = excluded.debut, fin = excluded.fin",
        (annee_id, libelle, debut, fin or debut),
    )


def supprimer_periode(annee_id: int, libelle: str) -> None:
    """Retire une période. Le pendant explicite du « début vide »."""
    garde_ecriture(annee_id)
    execute("DELETE FROM vacances WHERE annee_id = ? AND libelle = ?",
            (annee_id, libelle))


feature = Feature(
    name="calendrier_data",
    kind="data",
    provides=[
        horaires_de, trimestres_de, periodes_de, cours_perdus,
        modifier_annee, creer_annee, designer_en_cours, poser_trimestre,
        poser_periode, supprimer_periode,
    ],
    uses=["db", "annees"],
)
