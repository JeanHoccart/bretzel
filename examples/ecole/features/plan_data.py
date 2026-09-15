"""features/plan_data — data : les salles, les places, les contraintes.

``kind="data"``. Elle porte les règles d'EF-G qui vivent dans la donnée,
et deux d'entre elles sont des pièges MESURÉS de l'application d'origine.

**Piège n° 6 — une allée est un COULOIR, pas une case.** Le bouton
« allée » ouvre le passage sur TOUTE la colonne, pas sur la seule place
touchée (EF-G4). *« Un passage ouvert sur trois rangées et fermé sur
deux ne ressemble à aucune salle réelle. »* Le stockage reste par place,
le geste est par colonne, et c'est :func:`basculer_allee` qui tient la
différence.

**Piège n° 7 — la largeur d'allée décrit la SALLE, pas le cycle.** Une
seule valeur par salle (EF-G6). L'écrire en dur par cycle est ce qui
avait été fait, et c'est faux : deux secondes n'ont pas le même mobilier.

**EF-G10 — les contraintes sont attachées à la CLASSE, pas à la salle.**
*« Les ressaisir par salle serait une corvée doublée d'un risque de
divergence. »* Une classe reçue dans deux salles a donc deux plans et un
seul jeu de contraintes.
"""

from __future__ import annotations

import json
from datetime import date

from bretzel import Feature
from bretzel.state import AppState, field
from examples.ecole.core.db import execute, query, scalar
from examples.ecole.core.placement import rangees_du_gabarit
from examples.ecole.features.annees import garde_ecriture

#: Combien de versions on garde par salle (EF-G13).
VERSIONS_GARDEES = 6

#: Les bornes d'EF-G3 : douze rangées et douze places au plus.
MAX_RANGEES = 12
MAX_COLONNES = 12

#: Le tracé proposé par « tracer la salle » (EF-G2).
LARGEUR_ALLEE_DEFAUT = 60


class PlanRev(AppState):
    """Le jeton que les zones du plan surveillent.

    Même raison qu'``appreciations_data.FichesRev`` : une écriture en
    base ne touche aucun état typé, donc rien ne se re-rend sans lui.
    ``merge="add"`` pour qu'un dépôt et une répartition simultanés ne
    perdent pas un incrément.
    """

    rev: int = field(default=0, merge="add")


class ContraintesRev(AppState):
    """Le jeton de la COLONNE de droite — séparations, devants, versions.

    Un second jeton et pas une dépendance de plus sur :class:`PlanRev` :
    ce sont deux surfaces qui ne bougent pas ensemble. Asseoir un élève
    ne change ni une paire à séparer, ni la liste des versions ; cocher
    « devant » ne déplace personne.

    Mesuré le 2026-09-13 avant la coupe : vider une place renvoyait
    **248 ko**, dont la colonne entière — trente boutons d'élèves, les
    séparations, les versions — redessinée pour rien, à chaque geste de
    glisser. ``merge="add"``, même raison que ci-dessus.
    """

    rev: int = field(default=0, merge="add")


def salles_de(classe_id: int) -> list[dict]:
    """Les salles d'une classe, dans l'ordre des onglets (EF-G11)."""
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
    """Les places d'une salle, avec l'élève assis s'il y en a un."""
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
    """Les paires à séparer et les élèves à mettre devant (EF-G10)."""
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
    """Les paires à séparer, avec les noms — pour l'écran."""
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
    """Les formes de salle réutilisables (EF-G15) — sans aucune classe."""
    return query(
        "SELECT id, nom, rangees, allees, largeur_allee FROM gabarits_salle "
        "ORDER BY nom")


def premiere_salle(classe_id: int, annee_id: int) -> int:
    """La salle d'une classe, créée à la volée si elle n'en a pas (EF-G11).

    *« Une classe n'a pas de salle tant qu'on n'a pas ouvert son plan :
    la première est créée à la volée. »* Sans ça, l'écran s'ouvrirait sur
    un état vide qu'il faudrait « initialiser » — un geste de plus qui ne
    répond à aucune question.
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


# ── Les écritures ────────────────────────────────────────────────────

def tracer(salle_id: int, annee_id: int, longueurs: list[int],
           allees: list[int], largeur: int) -> None:
    """EF-G2 — *« la salle se trace d'un seul geste »*.

    Efface et refait : c'est une remise à zéro assumée, et l'écran le dit
    avant. Conserver les élèves assis en redessinant la salle donnerait
    des places « à moitié » gardées, ce qui est plus dur à comprendre
    qu'une grille vide.
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
    """Le ``−`` et le ``+`` d'EF-G3. Rend un refus, ou ``None``.

    *« Une place occupée refuse de partir. »* Le refus est rendu en
    PHRASE et pas en booléen : l'écran doit dire pourquoi, sinon le
    bouton a l'air cassé.
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
    """EF-G4 — le passage s'ouvre sur TOUTE la colonne, pas sur une place.

    C'est le piège n° 6, et il tient en une clause ``WHERE`` : ``colonne
    = ?`` et pas ``id = ?``. *« Seules bougent les rangées où la colonne
    visée existe »* — ce qui est vrai sans rien faire, puisque les autres
    n'ont pas de ligne pour cette colonne.

    EF-G5 : une allée devant la PREMIÈRE place est refusée.
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
    """EF-G6 — **une salle a un passage, pas dix largeurs.**"""
    garde_ecriture(annee_id)
    execute(
        "UPDATE places SET allee_avant = ? WHERE salle_id = ? "
        "AND allee_avant > 0", (max(0, min(largeur, 200)), salle_id))
    PlanRev().rev += 1


def asseoir(salle_id: int, annee_id: int, place_id: int,
            eleve_id: int | None) -> None:
    """Pose un élève sur une place — et l'ÉCHANGE si elle est prise.

    EF-G8 demande quatre gestes (glisser, vider, tout vider, échanger) ;
    trois d'entre eux sont ce même appel. L'échange n'est pas un cas
    particulier : un élève lâché sur une place occupée doit aller
    quelque part, et l'endroit d'où il vient est le seul qui soit libre.
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
    """Écrit une répartition entière."""
    garde_ecriture(annee_id)
    execute("UPDATE places SET eleve_id = NULL WHERE salle_id = ?",
            (salle_id,))
    for place_id, eleve_id in assises.items():
        execute("UPDATE places SET eleve_id = ? WHERE id = ?",
                (eleve_id, place_id))
    PlanRev().rev += 1


def figer(salle_id: int, annee_id: int, fige: bool) -> None:
    """EF-G14 — **le plan se fige, et l'état est RETENU**.

    *« Sur tablette, la main qui tient l'appareil effleure l'écran et
    déplace un élève sans que rien ne le signale — on s'en aperçoit au
    cours suivant, devant un plan faux. »* L'état vit en base et pas dans
    une session : *« on fige une fois pour l'année, pas à chaque heure »*.
    """
    garde_ecriture(annee_id)
    execute("UPDATE salles_plan SET fige = ? WHERE id = ?",
            (int(fige), salle_id))
    PlanRev().rev += 1


def ajouter_salle(classe_id: int, annee_id: int, nom: str,
                  demi_groupe: int | None) -> int:
    """Une seconde salle pour la même classe (EF-G11)."""
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
    """EF-G11 — **la DERNIÈRE salle ne se supprime pas.**

    *« "Effacer la grille" existe déjà pour repartir de zéro. »* Une
    classe sans aucune salle rouvrirait son plan sur une création à la
    volée, donc la suppression n'aurait rien supprimé — juste perdu les
    places.
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
    """EF-G13 — on fige un plan, six sont gardées par salle."""
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
    """Le CHOIX MANUEL d'EF-G9 — qui se cumule avec l'aménagement et la
    vue fragile, il ne les remplace pas."""
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
    """EF-G17 — répartir la classe en deux demi-groupes de TP."""
    garde_ecriture(annee_id)
    execute(
        "UPDATE inscriptions SET demi_groupe = ? WHERE eleve_id = ? "
        "AND classe_id = ? AND fin IS NULL", (groupe, eleve_id, classe_id))
    # Les DEUX : le demi-groupe change qui la salle assied *et* qui la
    # colonne des contraintes propose de mettre devant.
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
