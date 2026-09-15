"""features/appreciations_data — data : les fiches d'observation.

``kind="data"``. Elle porte EF-E1 à EF-E3 côté données, et **le drapeau
qui décide de tout** : ``ecrite_main``.

EF-E3, en une ligne de schéma
------------------------------
*« Dès que le professeur écrit son propre texte, l'application ne le
réécrit plus jamais — même si les observations changent ensuite. Un
bouton permet de redemander explicitement une proposition. »*

Trois comportements, un seul drapeau :

=========================  ======================================
geste                      ce que devient ``ecrite_main``
=========================  ======================================
cocher une observation     inchangé ; le texte est reproposé
                           **seulement s'il vaut 0**
écrire dans le champ       passe à 1, définitivement
cliquer « reproposer »     repasse à 0, et le texte est refait
=========================  ======================================

Sans ce drapeau, la seule façon de ne pas écraser serait de comparer le
texte à ce qu'on aurait proposé — ce qui échoue dès que le professeur
corrige une virgule.
"""

from __future__ import annotations

from bretzel import Feature
from bretzel.state import AppState, field
from examples.ecole.core.db import execute, query
from examples.ecole.core.domain import CRITERES
from examples.ecole.features.annees import garde_ecriture


class FichesRev(AppState):
    """Le jeton que les zones surveillent. Bumpé à chaque écriture.

    ⚠️ **Une écriture en base ne touche AUCUN état typé**, donc le
    moteur de re-render ne la voit pas. Sans ce jeton, cocher une
    tuile écrit correctement la fiche et **l'écran ne bouge pas** :
    pas d'erreur, pas de trace, le texte reste vide et on cherche le
    bug dans la fabrique d'appréciations.

    C'est le patron d'``examples/crm`` (``ContactsRev``), et il a été
    oublié ici jusqu'au probe : les écrans précédents marchaient par
    accident, parce que leurs handlers mutaient AUSSI un brouillon
    (``draft.ouvert = False``) et que cette mutation-là réveillait la
    zone.

    ``merge="add"`` et pas une affectation : deux écritures
    simultanées perdraient un incrément, et le jeton cesserait
    d'avancer aussi vite que les écritures.
    """

    rev: int = field(default=0, merge="add")


def criteres_et_niveaux() -> list[dict]:
    """Les quatre critères et leurs niveaux, dans l'ordre du bulletin.

    Une seule requête pour les vingt-quatre niveaux : quatre requêtes
    seraient plus lisibles et coûteraient quatre ouvertures de fichier
    par rendu de fiche.
    """
    lignes = query(
        """
        SELECT c.id AS critere_id, c.libelle AS critere, c.rang AS rang_critere,
               n.id AS niveau_id, n.rang, n.court, n.long, n.teinte
        FROM criteres c JOIN niveaux_critere n ON n.critere_id = c.id
        ORDER BY c.rang, n.rang
        """
    )
    par_critere: dict[str, dict] = {}
    for ligne in lignes:
        bloc = par_critere.setdefault(ligne["critere"], {
            "critere_id": ligne["critere_id"],
            "critere": ligne["critere"],
            "niveaux": [],
        })
        bloc["niveaux"].append({
            "id": ligne["niveau_id"], "rang": ligne["rang"],
            "court": ligne["court"], "long": ligne["long"],
            "teinte": ligne["teinte"],
        })
    return [par_critere[c] for c in CRITERES if c in par_critere]


def fiche_de(eleve_id: int, classe_id: int, trimestre: int) -> dict:
    """La fiche d'un élève, créée à la volée si elle n'existe pas.

    Une fiche vide n'est pas une absence de fiche : le trimestre existe,
    l'élève aussi, et l'écran doit pouvoir cocher. La créer à la LECTURE
    évite un « enregistrer d'abord » qui n'aurait aucun sens.
    """
    lignes = query(
        "SELECT id, appreciation, ecrite_main FROM fiches "
        "WHERE eleve_id = ? AND classe_id = ? AND trimestre = ?",
        (eleve_id, classe_id, trimestre))
    if not lignes:
        return {"id": 0, "appreciation": "", "ecrite_main": 0, "niveaux": {}}
    fiche = dict(lignes[0])
    fiche["niveaux"] = {
        r["critere"]: {"niveau_id": r["niveau_id"], "long": r["long"],
                       "teinte": r["teinte"], "court": r["court"]}
        for r in query(
            """
            SELECT c.libelle AS critere, n.id AS niveau_id, n.long, n.court,
                   n.teinte
            FROM fiches_niveaux fn
            JOIN criteres c ON c.id = fn.critere_id
            JOIN niveaux_critere n ON n.id = fn.niveau_critere_id
            WHERE fn.fiche_id = ?
            """,
            (fiche["id"],))
    }
    return fiche


def fiches_de_classe(classe_id: int, trimestre: int) -> list[dict]:
    """Toutes les appréciations d'une classe, pour la relecture (EF-E9)."""
    return query(
        """
        SELECT e.id AS eleve_id, e.nom, e.prenom,
               COALESCE(f.appreciation, '') AS appreciation,
               COALESCE(f.ecrite_main, 0) AS ecrite_main
        FROM inscriptions i
        JOIN eleves e ON e.id = i.eleve_id
        LEFT JOIN fiches f ON f.eleve_id = e.id AND f.classe_id = i.classe_id
                          AND f.trimestre = ?
        WHERE i.classe_id = ? AND i.fin IS NULL
        ORDER BY e.nom COLLATE NOCASE, e.prenom COLLATE NOCASE
        """,
        (trimestre, classe_id),
    )


def teintes_de_classe(classe_id: int, trimestre: int) -> dict[str, list[int]]:
    """``critère → [teintes cochées]`` — l'entrée du bilan (EF-F)."""
    resultat: dict[str, list[int]] = {}
    for ligne in query(
        """
        SELECT c.libelle AS critere, n.teinte
        FROM fiches f
        JOIN fiches_niveaux fn ON fn.fiche_id = f.id
        JOIN criteres c ON c.id = fn.critere_id
        JOIN niveaux_critere n ON n.id = fn.niveau_critere_id
        WHERE f.classe_id = ? AND f.trimestre = ?
        """,
        (classe_id, trimestre),
    ):
        resultat.setdefault(ligne["critere"], []).append(ligne["teinte"])
    return resultat


def phrase_du_niveau(niveau_id: int, trimestre: int) -> str:
    """La formulation d'EF-E5, celle du TRIMESTRE demandé.

    Repli sur le libellé long si la table n'a rien : une phrase manquante
    ne doit pas vider une appréciation.
    """
    lignes = query(
        "SELECT texte FROM phrases WHERE niveau_critere_id = ? "
        "AND trimestre = ?", (niveau_id, trimestre))
    if lignes:
        return lignes[0]["texte"]
    repli = query("SELECT long FROM niveaux_critere WHERE id = ?",
                  (niveau_id,))
    return repli[0]["long"] if repli else ""


# ── Les écritures ────────────────────────────────────────────────────

def assurer_fiche(eleve_id: int, classe_id: int, trimestre: int,
                  annee_id: int) -> int:
    garde_ecriture(annee_id)
    lignes = query(
        "SELECT id FROM fiches WHERE eleve_id = ? AND classe_id = ? "
        "AND trimestre = ?", (eleve_id, classe_id, trimestre))
    if lignes:
        return lignes[0]["id"]
    return execute(
        "INSERT INTO fiches (eleve_id, classe_id, trimestre, appreciation, "
        "ecrite_main) VALUES (?, ?, ?, '', 0)",
        (eleve_id, classe_id, trimestre))


def cocher(eleve_id: int, classe_id: int, trimestre: int, annee_id: int,
           critere_id: int, niveau_id: int | None) -> None:
    """Coche (ou décoche) un niveau. **Au plus un par critère** (EF-E1).

    C'est la clé primaire ``(fiche_id, critere_id)`` qui le garantit, pas
    un test ici : une règle tenue par le schéma tient quel que soit
    l'écran.
    """
    fiche_id = assurer_fiche(eleve_id, classe_id, trimestre, annee_id)
    if niveau_id is None:
        execute("DELETE FROM fiches_niveaux WHERE fiche_id = ? "
                "AND critere_id = ?", (fiche_id, critere_id))
        FichesRev().rev += 1
        return
    execute(
        "INSERT INTO fiches_niveaux (fiche_id, critere_id, niveau_critere_id) "
        "VALUES (?, ?, ?) "
        "ON CONFLICT (fiche_id, critere_id) DO UPDATE SET "
        "niveau_critere_id = excluded.niveau_critere_id",
        (fiche_id, critere_id, niveau_id))
    FichesRev().rev += 1


def proposer(eleve_id: int, classe_id: int, trimestre: int, annee_id: int,
             texte: str) -> bool:
    """Écrit une proposition — **sauf si le professeur a écrit** (EF-E3).

    Rend vrai si le texte a été posé. Le refus n'est pas une erreur :
    c'est le comportement attendu, et c'est pour ça que la fonction rend
    un booléen plutôt que de lever.
    """
    fiche_id = assurer_fiche(eleve_id, classe_id, trimestre, annee_id)
    lignes = query("SELECT ecrite_main FROM fiches WHERE id = ?", (fiche_id,))
    if lignes and lignes[0]["ecrite_main"]:
        return False
    execute("UPDATE fiches SET appreciation = ? WHERE id = ?",
            (texte[:600], fiche_id))
    FichesRev().rev += 1
    return True


def ecrire_a_la_main(eleve_id: int, classe_id: int, trimestre: int,
                     annee_id: int, texte: str) -> None:
    """Le professeur écrit : le drapeau tombe, **définitivement**."""
    fiche_id = assurer_fiche(eleve_id, classe_id, trimestre, annee_id)
    execute(
        "UPDATE fiches SET appreciation = ?, ecrite_main = 1 WHERE id = ?",
        (texte[:600], fiche_id))
    FichesRev().rev += 1


def redemander(eleve_id: int, classe_id: int, trimestre: int,
               annee_id: int) -> None:
    """Le bouton d'EF-E3 : *« redemander explicitement une proposition »*.

    C'est la SEULE façon de repasser ``ecrite_main`` à zéro. Sans elle,
    une correction malheureuse condamnerait la fiche à rester telle
    quelle jusqu'à la fin de l'année.
    """
    fiche_id = assurer_fiche(eleve_id, classe_id, trimestre, annee_id)
    execute("UPDATE fiches SET ecrite_main = 0 WHERE id = ?", (fiche_id,))
    FichesRev().rev += 1


feature = Feature(
    name="appreciations_data",
    kind="data",
    provides=[
        FichesRev,
        criteres_et_niveaux, fiche_de, fiches_de_classe, teintes_de_classe,
        phrase_du_niveau, assurer_fiche, cocher, proposer, ecrire_a_la_main,
        redemander,
    ],
    uses=["db", "annees"],
)
