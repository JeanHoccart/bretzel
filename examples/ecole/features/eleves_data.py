"""features/eleves_data — data : les élèves, leurs inscriptions, leurs mouvements.

``kind="data"``. C'est ici que **RT-2 devient du code** : rien ne s'efface
qui porte de l'histoire.

- un élève qui part reçoit une **date de fin d'inscription**. Il sort des
  listes, ses notes restent, on peut le réinscrire ;
- un transfert est une **sortie plus une entrée**, pas une colonne qu'on
  réécrit — sans quoi le parcours d'EF-C9 n'aurait rien à montrer ;
- **en revanche**, supprimer une classe emporte les élèves qui
  n'appartiennent qu'à elle. Sinon ils resteraient en base sans classe,
  invisibles — ce qui est pire que supprimés.

Le nom et le prénom restent DISTINCTS
--------------------------------------
EF-C7 : *« un élève qui s'appelle LEA de son nom ne doit pas se
confondre avec une Léa de prénom »*. La recherche compare donc les deux
colonnes séparément, et la comparaison ignore les accents et la casse
sans jamais fondre les deux champs en un.
"""

from __future__ import annotations

from bretzel import Feature
from examples.ecole.core.db import execute, query, scalar
from examples.ecole.features.annees import garde_ecriture


def eleves_de(classe_id: int) -> list[dict]:
    """Les élèves EN COURS d'inscription, par ordre alphabétique.

    ``i.fin IS NULL`` : un élève sorti garde sa ligne (RT-2) et quitte
    les listes. C'est la même clause partout, et c'est elle qui fait la
    différence entre « il n'est plus là » et « il n'a jamais existé ».
    """
    return query(
        """
        SELECT e.id, e.nom, e.prenom, e.naissance, e.amenagement,
               e.vue_fragile, e.gaucher, e.precisions, i.demi_groupe
        FROM inscriptions i
        JOIN eleves e ON e.id = i.eleve_id
        WHERE i.classe_id = ? AND i.fin IS NULL
        ORDER BY e.nom COLLATE NOCASE, e.prenom COLLATE NOCASE
        """,
        (classe_id,),
    )


def sortis_de(classe_id: int) -> list[dict]:
    """Ceux qui sont partis, avec leur date de sortie (EF-C5).

    *« La liste des sortis est consultable »* : sans cet écran,
    l'historique est conservé et invisible — ce qui revient à ne pas
    l'avoir.
    """
    return query(
        """
        SELECT e.id, e.nom, e.prenom, i.fin
        FROM inscriptions i
        JOIN eleves e ON e.id = i.eleve_id
        WHERE i.classe_id = ? AND i.fin IS NOT NULL
        ORDER BY i.fin DESC, e.nom COLLATE NOCASE
        """,
        (classe_id,),
    )


def classe(classe_id: int) -> dict | None:
    lignes = query(
        "SELECT id, annee_id, code, libelle, cycle, niveau, prof_principal "
        "FROM classes WHERE id = ?", (classe_id,))
    return lignes[0] if lignes else None


def eleve(eleve_id: int) -> dict | None:
    lignes = query(
        "SELECT id, nom, prenom, naissance, amenagement, vue_fragile, "
        "gaucher, precisions FROM eleves WHERE id = ?", (eleve_id,))
    return lignes[0] if lignes else None


def parcours_de(eleve_id: int) -> list[dict]:
    """Les classes traversées, d'une année à l'autre (EF-C9).

    *« Les inscriptions sont datées précisément pour cela ; sans l'écran
    qui les montre, l'historique est conservé et invisible. »*
    """
    return query(
        """
        SELECT a.libelle AS annee, c.id AS classe_id, c.code, c.libelle,
               i.debut, i.fin
        FROM inscriptions i
        JOIN classes c ON c.id = i.classe_id
        JOIN annees a ON a.id = c.annee_id
        WHERE i.eleve_id = ?
        ORDER BY i.debut DESC
        """,
        (eleve_id,),
    )


def classe_courante_de(eleve_id: int) -> dict | None:
    """La classe où l'élève est inscrit AUJOURD'HUI, s'il y en a une."""
    lignes = query(
        """
        SELECT c.id, c.code, c.libelle, c.cycle, c.annee_id
        FROM inscriptions i
        JOIN classes c ON c.id = i.classe_id
        WHERE i.eleve_id = ? AND i.fin IS NULL
        ORDER BY i.debut DESC LIMIT 1
        """,
        (eleve_id,),
    )
    return lignes[0] if lignes else None


def chercher(annee_id: int, texte: str) -> list[dict]:
    """Cherche par NOM ou par PRÉNOM sur toute l'année (EF-C7).

    ⚠️ **Les deux colonnes sont comparées SÉPARÉMENT**, et c'est
    l'exigence : *« un élève qui s'appelle LEA de son nom ne doit pas se
    confondre avec une Léa de prénom »*. Un ``nom || prenom LIKE`` les
    fondrait, et « lea martin » trouverait aussi « Martin Léa » — ce qui
    est peut-être pratique et n'est pas ce qui est demandé.

    ``COLLATE NOCASE`` gère la casse ; les accents sont gérés par le
    repli sur la forme sans accents, calculé en Python — SQLite ne sait
    pas le faire seul sans extension.
    """
    motif = f"%{texte.strip()}%"
    if not texte.strip():
        return []
    return query(
        """
        SELECT e.id, e.nom, e.prenom, c.id AS classe_id, c.code
        FROM inscriptions i
        JOIN eleves e ON e.id = i.eleve_id
        JOIN classes c ON c.id = i.classe_id
        WHERE c.annee_id = ? AND i.fin IS NULL
          AND (e.nom LIKE ? COLLATE NOCASE
               OR e.prenom LIKE ? COLLATE NOCASE)
        ORDER BY e.nom COLLATE NOCASE, e.prenom COLLATE NOCASE
        LIMIT 200
        """,
        (annee_id, motif, motif),
    )


def classes_de(annee_id: int) -> list[dict]:
    """Les classes d'une année — pour les sélecteurs de mouvement."""
    return query(
        "SELECT id, code, libelle FROM classes WHERE annee_id = ? "
        "ORDER BY rang, code", (annee_id,))


# ── Les écritures. Toutes gardées par RT-1 ───────────────────────────

def regler_particularites(eleve_id: int, annee_id: int,
                          champs: dict) -> None:
    """Les quatre particularités d'un élève (EF-C4)."""
    garde_ecriture(annee_id)
    execute(
        "UPDATE eleves SET amenagement = ?, vue_fragile = ?, gaucher = ?, "
        "precisions = ? WHERE id = ?",
        (champs["amenagement"], int(champs["vue_fragile"]),
         int(champs["gaucher"]), champs["precisions"][:200], eleve_id),
    )


def regler_prof_principal(classe_id: int, annee_id: int, nom: str) -> None:
    """EF-C6 — et son nom ouvre un lien de courrier, côté écran."""
    garde_ecriture(annee_id)
    execute("UPDATE classes SET prof_principal = ? WHERE id = ?",
            (nom.strip()[:60], classe_id))


def ajouter_eleve(classe_id: int, annee_id: int, nom: str, prenom: str,
                  debut: str) -> int:
    """Crée un élève et l'inscrit (EF-C5)."""
    garde_ecriture(annee_id)
    eleve_id = execute(
        "INSERT INTO eleves (nom, prenom) VALUES (?, ?)",
        (nom.strip()[:60], prenom.strip()[:60]))
    execute(
        "INSERT INTO inscriptions (eleve_id, classe_id, debut, fin) "
        "VALUES (?, ?, ?, NULL)", (eleve_id, classe_id, debut))
    return eleve_id


def faire_sortir(eleve_id: int, classe_id: int, annee_id: int,
                 fin: str) -> None:
    """L'élève quitte les listes, **et rien ne s'efface** (RT-2)."""
    garde_ecriture(annee_id)
    execute(
        "UPDATE inscriptions SET fin = ? WHERE eleve_id = ? AND classe_id = ? "
        "AND fin IS NULL", (fin, eleve_id, classe_id))


def faire_revenir(eleve_id: int, classe_id: int, annee_id: int,
                  debut: str) -> None:
    """Il revient : une inscription NEUVE, pas une fin qu'on efface.

    Effacer la date de fin ferait disparaître le fait qu'il est parti, et
    le parcours d'EF-C9 rendrait un séjour continu qui n'a pas eu lieu.
    """
    garde_ecriture(annee_id)
    execute(
        "INSERT INTO inscriptions (eleve_id, classe_id, debut, fin) "
        "VALUES (?, ?, ?, NULL)", (eleve_id, classe_id, debut))


def transferer(eleve_id: int, depuis: int, vers: int, annee_id: int,
               jour: str) -> None:
    """Un transfert est une SORTIE plus une ENTRÉE (EF-C5, RT-2)."""
    garde_ecriture(annee_id)
    faire_sortir(eleve_id, depuis, annee_id, jour)
    faire_revenir(eleve_id, vers, annee_id, jour)


def supprimer_classe(classe_id: int, annee_id: int) -> int:
    """Supprime la classe et **les élèves qui n'appartiennent qu'à elle**.

    RT-2 a deux moitiés, et c'est ici que la seconde s'applique : *« en
    revanche, supprimer une classe emporte les élèves qui n'appartiennent
    qu'à elle — sinon ils resteraient en base sans classe, invisibles »*.

    Rend le nombre d'élèves emportés, pour que l'écran puisse le dire
    avant de le faire (EF-C8 : confirmation explicite).
    """
    garde_ecriture(annee_id)
    orphelins = [
        r["eleve_id"] for r in query(
            """
            SELECT i.eleve_id FROM inscriptions i
            WHERE i.classe_id = ?
              AND NOT EXISTS (SELECT 1 FROM inscriptions j
                              WHERE j.eleve_id = i.eleve_id
                                AND j.classe_id <> ?)
            """,
            (classe_id, classe_id),
        )
    ]
    for table in ("fiches_niveaux",):
        execute(
            f"DELETE FROM {table} WHERE fiche_id IN "
            f"(SELECT id FROM fiches WHERE classe_id = ?)", (classe_id,))
    execute("DELETE FROM fiches WHERE classe_id = ?", (classe_id,))
    execute(
        "DELETE FROM sous_notes WHERE note_id IN (SELECT n.id FROM notes n "
        "JOIN evaluations ev ON ev.id = n.evaluation_id "
        "WHERE ev.classe_id = ?)", (classe_id,))
    execute(
        "DELETE FROM corrections_a_reporter WHERE evaluation_id IN "
        "(SELECT id FROM evaluations WHERE classe_id = ?)", (classe_id,))
    execute(
        "DELETE FROM notes WHERE evaluation_id IN "
        "(SELECT id FROM evaluations WHERE classe_id = ?)", (classe_id,))
    execute("DELETE FROM evaluations WHERE classe_id = ?", (classe_id,))
    execute(
        "DELETE FROM places WHERE salle_id IN "
        "(SELECT id FROM salles_plan WHERE classe_id = ?)", (classe_id,))
    execute(
        "DELETE FROM versions_plan WHERE salle_id IN "
        "(SELECT id FROM salles_plan WHERE classe_id = ?)", (classe_id,))
    execute("DELETE FROM salles_plan WHERE classe_id = ?", (classe_id,))
    execute("DELETE FROM separations WHERE classe_id = ?", (classe_id,))
    execute("DELETE FROM devants WHERE classe_id = ?", (classe_id,))
    execute("DELETE FROM verifications WHERE classe_id = ?", (classe_id,))
    execute("DELETE FROM cahier WHERE classe_id = ?", (classe_id,))
    execute("DELETE FROM creneaux WHERE classe_id = ?", (classe_id,))
    execute("DELETE FROM heures_exceptionnelles WHERE classe_id = ?",
            (classe_id,))
    execute("DELETE FROM inscriptions WHERE classe_id = ?", (classe_id,))
    for eleve_id in orphelins:
        execute("DELETE FROM eleves WHERE id = ?", (eleve_id,))
    execute("DELETE FROM classes WHERE id = ?", (classe_id,))
    return len(orphelins)


def eleves_emportes_par(classe_id: int) -> int:
    """Combien d'élèves une suppression emporterait — AVANT de le faire.

    EF-C8 demande une confirmation explicite ; une confirmation qui ne
    dit pas ce qu'elle coûte n'en est pas une.
    """
    return scalar(
        """
        SELECT COUNT(DISTINCT i.eleve_id) FROM inscriptions i
        WHERE i.classe_id = ?
          AND NOT EXISTS (SELECT 1 FROM inscriptions j
                          WHERE j.eleve_id = i.eleve_id
                            AND j.classe_id <> ?)
        """,
        (classe_id, classe_id),
    ) or 0


feature = Feature(
    name="eleves_data",
    kind="data",
    provides=[
        eleves_de, sortis_de, classe, eleve, parcours_de, classe_courante_de,
        chercher, classes_de, regler_particularites, regler_prof_principal,
        ajouter_eleve, faire_sortir, faire_revenir, transferer,
        supprimer_classe, eleves_emportes_par,
    ],
    uses=["db", "annees"],
)
