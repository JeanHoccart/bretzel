"""features/cahier_data — data : le cahier de texte, la progression, les fiches.

``kind="data"``. EF-K1 à EF-K12, EF-L1 à EF-L3, EF-M1 à EF-M4.

EF-K2 — **le geste visé est celui du soir**
---------------------------------------------
*« Ouvrir, vérifier, recopier sur École Directe. Tout le reste est là
pour épargner de la frappe. »* Cinq pré-remplissages, et le cinquième est
le seul qui ne se devine pas :

1. la classe du MOMENT, d'après l'emploi du temps ;
2. le chapitre de la dernière séance de cette classe ;
3. la séance SUIVANTE, pour cette classe ;
4. le texte pré-rempli avec les deux titres ;
5. **le chapitre n'est annoncé qu'une fois par classe.** *« Répété à
   chaque séance, il noierait le titre du jour sur École Directe. »*

EF-K5 — le cahier lit la GRILLE **et** les exceptions
------------------------------------------------------
*« Jamais la grille seule — sinon il proposerait de noter une classe
qu'on n'a pas eue. »* C'est pour ça que :func:`prochaines_heures` passe
par ``grille_data.semaine_affichee``, qui mélange déjà les trois sources,
au lieu de relire ``creneaux``.

EF-M3 — une fiche est rattachée par le TITRE, jamais par le numéro
-------------------------------------------------------------------
**Piège n° 10.** *« Un numéro glisse dès qu'on insère une séance en cours
d'année : toutes les fiches suivantes se retrouveraient sur la voisine,
sans que rien ne le dise. »* La clé de ``fiches_seance`` est donc
``(chapitre_id, seance_titre)``, et le numéro n'est qu'une position du
jour.
"""

from __future__ import annotations

from datetime import date, timedelta

from bretzel import Feature
from bretzel.state import AppState, field
from examples.ecole.core.db import execute, query
from examples.ecole.core.domain import est_un_tp, niveau_du_code
from examples.ecole.features.annees import garde_ecriture


class CahierRev(AppState):
    """Le jeton des zones du cahier. Même raison que les autres."""

    rev: int = field(default=0, merge="add")


def entrees_de(classe_id: int, croissant: bool = False) -> list[dict]:
    """Les entrées d'une classe (EF-K8).

    *« La liste d'une classe se lit la séance du jour en tête. L'archive,
    elle, se lit dans l'ordre chronologique croissant, septembre en haut.
    Ce n'est pas le même objet : un écran se consulte, une archive se lit
    du début à la fin. »* D'où le paramètre, et son défaut.
    """
    sens = "ASC" if croissant else "DESC"
    return query(
        f"""
        SELECT ca.id, ca.date, ca.seance_numero, ca.seance_titre,
               ca.contenu, ca.travail, ca.reporte_le, ca.chapitre_id,
               ch.titre AS chapitre
        FROM cahier ca LEFT JOIN chapitres ch ON ch.id = ca.chapitre_id
        WHERE ca.classe_id = ?
        ORDER BY ca.date {sens}, ca.id {sens}
        """,
        (classe_id,),
    )


def entree(entree_id: int) -> dict | None:
    lignes = query(
        """
        SELECT ca.*, c.code, c.annee_id, c.niveau, ch.titre AS chapitre
        FROM cahier ca JOIN classes c ON c.id = ca.classe_id
        LEFT JOIN chapitres ch ON ch.id = ca.chapitre_id
        WHERE ca.id = ?
        """,
        (entree_id,),
    )
    return lignes[0] if lignes else None


def chapitres_du_niveau(niveau: str) -> list[dict]:
    """Les chapitres d'un niveau (EF-L3).

    *« Le niveau rapproche une classe d'un chapitre par le début de son
    code. »* Le rapprochement passe par
    :func:`~examples.ecole.core.domain.niveau_du_code`, qui est l'unique
    façon de le faire dans toute l'application.
    """
    return query(
        "SELECT id, titre, rang FROM chapitres WHERE niveau = ? "
        "ORDER BY rang", (niveau,))


def seances_de(chapitre_id: int) -> list[dict]:
    return query(
        "SELECT id, numero, titre FROM seances_chapitre WHERE chapitre_id = ? "
        "ORDER BY numero", (chapitre_id,))


def derniere_entree(classe_id: int) -> dict | None:
    lignes = entrees_de(classe_id)
    return lignes[0] if lignes else None


def deja_notee(classe_id: int, chapitre_id: int, titre: str) -> bool:
    """EF-K11 — *« rien n'est proposé si la classe a déjà noté cette
    séance : ce serait l'inviter à l'écrire deux fois »*."""
    return bool(query(
        "SELECT 1 FROM cahier WHERE classe_id = ? AND chapitre_id = ? "
        "AND seance_titre = ? LIMIT 1", (classe_id, chapitre_id, titre)))


def chapitre_deja_annonce(classe_id: int, chapitre_id: int) -> bool:
    """EF-K2 § 5 — **le chapitre n'est annoncé qu'une fois par classe.**

    *« Répété à chaque séance, il noierait le titre du jour sur École
    Directe. »* Et c'est PAR CLASSE, ce qui est la raison pour laquelle
    reprendre une entrée pour une classe sœur bouge cette ligne-là et
    rien d'autre (EF-K9).
    """
    return bool(query(
        "SELECT 1 FROM cahier WHERE classe_id = ? AND chapitre_id = ? LIMIT 1",
        (classe_id, chapitre_id)))


def proposition(classe_id: int, niveau: str) -> dict:
    """Ce que le formulaire du soir doit déjà porter (EF-K2).

    Rend ``{chapitre_id, chapitre, numero, titre, contenu, travail}``.
    Les quatre pré-remplissages se lisent dans l'ordre du cahier ; le
    cinquième — l'annonce du chapitre — est la ligne conditionnelle du
    ``contenu``.
    """
    chapitres = chapitres_du_niveau(niveau)
    if not chapitres:
        return {"chapitre_id": None, "chapitre": "", "numero": 1,
                "titre": "", "contenu": "", "travail": ""}

    derniere = derniere_entree(classe_id)
    chapitre = next(
        (c for c in chapitres if c["id"] == (derniere or {}).get("chapitre_id")),
        chapitres[0],
    )
    seances = seances_de(chapitre["id"])
    suivante = next(
        (s for s in seances
         if not deja_notee(classe_id, chapitre["id"], s["titre"])),
        None,
    )
    if suivante is None:
        # Le chapitre est fini pour cette classe : on passe au suivant.
        rang = chapitres.index(chapitre)
        chapitre = chapitres[min(rang + 1, len(chapitres) - 1)]
        seances = seances_de(chapitre["id"])
        suivante = next(
            (s for s in seances
             if not deja_notee(classe_id, chapitre["id"], s["titre"])),
            seances[0] if seances else None,
        )
    if suivante is None:
        return {"chapitre_id": chapitre["id"], "chapitre": chapitre["titre"],
                "numero": 1, "titre": "", "contenu": "", "travail": ""}

    annonce = ("" if chapitre_deja_annonce(classe_id, chapitre["id"])
               else f"{chapitre['titre']}.\n")
    return {
        "chapitre_id": chapitre["id"],
        "chapitre": chapitre["titre"],
        "numero": suivante["numero"],
        "titre": suivante["titre"],
        "contenu": f"{annonce}Séance {suivante['numero']} : "
                   f"{suivante['titre']}.",
        "travail": "",
    }


def ce_qua_note_une_soeur(classe_id: int, niveau: str, chapitre_id: int,
                          titre: str) -> list[dict]:
    """EF-K10 — *« ce qu'une classe sœur a noté pour la même séance »*.

    *« Le geste : on est sur la 4e2, on cherche ce que la 4e1 a fait.
    Sans cela il faut aller sur la 4e1, retrouver la séance et la pousser
    — l'inverse du sens dans lequel on pense. »*

    Rien n'est rendu si CETTE classe a déjà noté la séance (EF-K11).
    """
    if not titre or deja_notee(classe_id, chapitre_id, titre):
        return []
    return query(
        """
        SELECT ca.id, ca.contenu, ca.travail, c.code
        FROM cahier ca JOIN classes c ON c.id = ca.classe_id
        WHERE ca.chapitre_id = ? AND ca.seance_titre = ?
          AND ca.classe_id <> ?
        ORDER BY ca.date DESC LIMIT 3
        """,
        (chapitre_id, titre, classe_id),
    )


def reprendre(contenu: str, chapitre: str, annoncer: bool) -> str:
    """EF-K9 — *« le texte est AJUSTÉ, jamais recalculé »*.

    *« Une première version le recomposait depuis le chapitre, et jetait
    donc tout ce qui avait été écrit à la main — or c'est exactement ce
    qu'on veut reprendre. Seule la ligne d'annonce du chapitre bouge,
    parce que la règle "le chapitre n'est annoncé qu'une fois" est PAR
    CLASSE. »*

    Donc : on retire l'annonce si elle est là et qu'elle ne doit pas y
    être, on l'ajoute si elle doit y être. Le reste du texte n'est jamais
    touché.
    """
    lignes = contenu.split("\n")
    annonce = f"{chapitre}."
    portait = bool(lignes) and lignes[0].strip() == annonce
    corps = lignes[1:] if portait else lignes
    if annoncer:
        return "\n".join([annonce, *corps])
    return "\n".join(corps).lstrip("\n")


def prochaines_heures(annee: dict, depuis: date, jours: int = 7) -> list[dict]:
    """Les heures à venir, **grille ET exceptions** (EF-K5, EF-K6, EF-K7).

    - une heure ANNULÉE n'y est pas, et n'est plus proposée comme prochain
      cours (EF-K5) ;
    - un jour de vacances n'y est pas non plus (EF-K6 : *« le cahier ne
      propose jamais de travail pour le lundi 26 octobre si ce lundi
      tombe en vacances »*) ;
    - une heure à NATURE n'a pas de séance à consigner (EF-K7).

    Et chaque heure dit si c'est un **TP de trois heures** (EF-K12), par
    la règle unique de ``domain.est_un_tp`` : *« une seule définition du
    TP dans toute l'application, jamais deux »*.
    """
    from examples.ecole.features.grille_data import (
        lundi_affiche,
        semaine_affichee,
    )

    heures: list[dict] = []
    lundi = lundi_affiche(annee, depuis.isoformat())
    for decalage in (0, 1):
        semaine = semaine_affichee(annee, lundi + timedelta(weeks=decalage))
        for jour in semaine["jours"]:
            if jour["periode"] or not (depuis <= jour["date"]
                                       <= depuis + timedelta(days=jours)):
                continue
            for bloc in jour["blocs"]:
                if bloc["nature"]:
                    continue
                heures.append({
                    "date": jour["date"],
                    "code": bloc["code"],
                    "tp": est_un_tp(bloc),
                    "heures": bloc["fin"] - bloc["debut"] + 1,
                })
    return sorted(heures, key=lambda h: (h["date"], h["code"]))


def progression(annee_id: int, niveau: str) -> dict:
    """EF-L1 — **un tableau, pas une liste.**

    *« Une ligne par classe, une colonne par chapitre, et dans chaque
    case où elle en est. »* Le besoin derrière : *« cinq classes sur un
    même programme dérivent l'une de l'autre sans qu'on s'en aperçoive,
    et on le découvre en juin quand il est trop tard »* — donc le
    décalage doit se lire COLONNE PAR COLONNE, pas en lisant cinq cahiers
    l'un après l'autre.
    """
    chapitres = chapitres_du_niveau(niveau)
    classes = [
        c for c in query(
            "SELECT id, code FROM classes WHERE annee_id = ? ORDER BY rang, code",
            (annee_id,))
        if niveau_du_code(c["code"]) == niveau
    ]
    faites: dict[tuple[int, int], int] = {}
    for ligne in query(
        """
        SELECT ca.classe_id, ca.chapitre_id, COUNT(*) AS n
        FROM cahier ca JOIN classes c ON c.id = ca.classe_id
        WHERE c.annee_id = ? AND ca.chapitre_id IS NOT NULL
        GROUP BY ca.classe_id, ca.chapitre_id
        """,
        (annee_id,),
    ):
        faites[(ligne["classe_id"], ligne["chapitre_id"])] = ligne["n"]
    totaux = {
        c["id"]: len(seances_de(c["id"])) for c in chapitres
    }
    return {"chapitres": chapitres, "classes": classes, "faites": faites,
            "totaux": totaux}


def niveaux_enseignes(annee_id: int) -> list[str]:
    vus: list[str] = []
    for ligne in query(
        "SELECT code FROM classes WHERE annee_id = ? ORDER BY rang, code",
        (annee_id,),
    ):
        niveau = niveau_du_code(ligne["code"])
        if niveau and niveau not in vus:
            vus.append(niveau)
    return vus


# ── Les fiches de séance (EF-M) ──────────────────────────────────────

def fiche_seance(chapitre_id: int, titre: str) -> dict | None:
    """La fiche d'une séance, **par son TITRE** (EF-M3, piège n° 10)."""
    lignes = query(
        "SELECT id, resume FROM fiches_seance WHERE chapitre_id = ? "
        "AND seance_titre = ?", (chapitre_id, titre))
    if not lignes:
        return None
    fiche = dict(lignes[0])
    fiche["notes"] = query(
        "SELECT id, carnet, texte, cree_le FROM notes_fiche "
        "WHERE fiche_seance_id = ? ORDER BY cree_le, id", (fiche["id"],))
    return fiche


def fiches_du_chapitre(chapitre_id: int) -> dict[str, dict]:
    """Les fiches d'un chapitre, indexées par TITRE de séance."""
    return {
        r["seance_titre"]: {"id": r["id"], "resume": r["resume"]}
        for r in query(
            "SELECT id, seance_titre, resume FROM fiches_seance "
            "WHERE chapitre_id = ?", (chapitre_id,))
    }


def fiches_orphelines(chapitre_id: int) -> list[str]:
    """EF-M4 — celles qu'on n'a pas pu rattacher, **signalées**.

    *« Une séance renommée, insérée ou supprimée doit laisser les fiches
    là où elles vont, et SIGNALER celles qu'on n'a pas pu rattacher
    plutôt que de les poser au hasard. »* Une fiche dont le titre ne
    correspond à aucune séance du chapitre est donc dite, pas
    réaffectée — la réaffecter au hasard est précisément le piège n° 10.
    """
    titres = {s["titre"] for s in seances_de(chapitre_id)}
    return [t for t in fiches_du_chapitre(chapitre_id) if t not in titres]


# ── Les écritures ────────────────────────────────────────────────────

def poser_entree(classe_id: int, annee_id: int, champs: dict) -> int:
    garde_ecriture(annee_id)
    entree_id = execute(
        "INSERT INTO cahier (classe_id, date, chapitre_id, seance_numero, "
        "seance_titre, contenu, travail, reporte_le) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, NULL)",
        (classe_id, champs["date"], champs["chapitre_id"],
         champs["numero"], champs["titre"], champs["contenu"],
         champs["travail"]))
    CahierRev().rev += 1
    return entree_id


def modifier_entree(entree_id: int, annee_id: int, champs: dict) -> None:
    garde_ecriture(annee_id)
    execute(
        "UPDATE cahier SET date = ?, chapitre_id = ?, seance_numero = ?, "
        "seance_titre = ?, contenu = ?, travail = ? WHERE id = ?",
        (champs["date"], champs["chapitre_id"], champs["numero"],
         champs["titre"], champs["contenu"], champs["travail"], entree_id))
    CahierRev().rev += 1


def marquer_reportee(entree_id: int, annee_id: int) -> None:
    """EF-K4 — comme les notes (EF-D7), avec la date."""
    garde_ecriture(annee_id)
    execute("UPDATE cahier SET reporte_le = ? WHERE id = ?",
            (date.today().isoformat(), entree_id))
    CahierRev().rev += 1


def supprimer_entree(entree_id: int, annee_id: int) -> None:
    garde_ecriture(annee_id)
    execute("DELETE FROM cahier WHERE id = ?", (entree_id,))
    CahierRev().rev += 1


def ecrire_resume(chapitre_id: int, titre: str, annee_id: int,
                  resume: str) -> None:
    """EF-M2 — le résumé se RÉÉCRIT. C'est la moitié qu'on corrige."""
    garde_ecriture(annee_id)
    execute(
        "INSERT INTO fiches_seance (chapitre_id, seance_titre, resume) "
        "VALUES (?, ?, ?) "
        "ON CONFLICT (chapitre_id, seance_titre) DO UPDATE SET "
        "resume = excluded.resume",
        (chapitre_id, titre, resume[:1000]))
    CahierRev().rev += 1


def ajouter_note(chapitre_id: int, titre: str, annee_id: int, carnet: str,
                 texte: str) -> None:
    """EF-M2 — les deux carnets où l'on AJOUTE.

    *« Chaque note est datée et NE REMPLACE PAS la précédente : la même
    séance donnée à la 3e2 puis à la 3e9, ce sont deux observations. »*
    C'est un ``INSERT``, jamais un ``UPDATE``, et c'est toute la
    différence avec le résumé juste au-dessus.
    """
    garde_ecriture(annee_id)
    lignes = query(
        "SELECT id FROM fiches_seance WHERE chapitre_id = ? "
        "AND seance_titre = ?", (chapitre_id, titre))
    if lignes:
        fiche_id = lignes[0]["id"]
    else:
        fiche_id = execute(
            "INSERT INTO fiches_seance (chapitre_id, seance_titre, resume) "
            "VALUES (?, ?, '')", (chapitre_id, titre))
    execute(
        "INSERT INTO notes_fiche (fiche_seance_id, carnet, texte, cree_le) "
        "VALUES (?, ?, ?, ?)",
        (fiche_id, carnet, texte[:500], date.today().isoformat()))
    CahierRev().rev += 1


feature = Feature(
    name="cahier_data",
    kind="data",
    provides=[
        CahierRev, entrees_de, entree, chapitres_du_niveau, seances_de,
        derniere_entree, deja_notee, chapitre_deja_annonce, proposition,
        ce_qua_note_une_soeur, reprendre, prochaines_heures, progression,
        niveaux_enseignes, fiche_seance, fiches_du_chapitre,
        fiches_orphelines, poser_entree, modifier_entree, marquer_reportee,
        supprimer_entree, ecrire_resume, ajouter_note,
    ],
    uses=["db", "annees", "grille_data"],
)
