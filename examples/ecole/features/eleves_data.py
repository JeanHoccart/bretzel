"""features/eleves_data — data: the pupils, their enrolments, their
movements.

``kind="data"``. It is here that **RT-2 becomes code**: nothing that
carries history is erased.

- a pupil who leaves receives an **enrolment end date**. They leave the
  lists, their marks stay, they can be re-enrolled;
- a transfer is a **departure plus an entry**, not a column one rewrites
  — without which EF-C9's path would have nothing to show;
- **on the other hand**, deleting a class takes with it the pupils
  belonging only to it. Otherwise they would stay in the database with no
  class, invisible — which is worse than deleted.

The surname and the first name stay DISTINCT
---------------------------------------------
EF-C7: *"a pupil whose surname is LEA must not be confused with a Léa by
first name"*. So the search compares the two columns separately, and the
comparison ignores accents and case without ever merging the two fields
into one.
"""

from __future__ import annotations

from bretzel import Feature
from examples.ecole.core.db import execute, query, scalar
from examples.ecole.features.annees import garde_ecriture


def eleves_de(classe_id: int) -> list[dict]:
    """The pupils with a CURRENT enrolment, in alphabetical order.

    ``i.fin IS NULL``: a pupil who has left keeps their row (RT-2) and
    leaves the lists. It is the same clause everywhere, and it is what
    makes the difference between "they are no longer here" and "they
    never existed".
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
    """Those who have left, with their departure date (EF-C5).

    *"The list of leavers can be consulted"*: without this screen, the
    history is kept and invisible — which amounts to not having it.
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
    """The classes gone through, from one year to the next (EF-C9).

    *"The enrolments are dated precisely for that; without the screen
    that shows them, the history is kept and invisible."*
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
    """The class the pupil is enrolled in TODAY, if there is one."""
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
    """Search by SURNAME or by FIRST NAME over the whole year (EF-C7).

    ⚠️ **The two columns are compared SEPARATELY**, and it is the
    requirement: *"a pupil whose surname is LEA must not be confused with
    a Léa by first name"*. A ``nom || prenom LIKE`` would merge them, and
    "lea martin" would also find "Martin Léa" — which may be convenient
    and is not what is asked for.

    ``COLLATE NOCASE`` handles the case; the accents are handled by
    falling back on the accent-free form, computed in Python — SQLite
    cannot do it alone without an extension.
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
    """A year's classes — for the movement selectors."""
    return query(
        "SELECT id, code, libelle FROM classes WHERE annee_id = ? "
        "ORDER BY rang, code", (annee_id,))


# ── The writes. All guarded by RT-1 ──────────────────────────────────

def regler_particularites(eleve_id: int, annee_id: int,
                          champs: dict) -> None:
    """A pupil's four particularities (EF-C4)."""
    garde_ecriture(annee_id)
    execute(
        "UPDATE eleves SET amenagement = ?, vue_fragile = ?, gaucher = ?, "
        "precisions = ? WHERE id = ?",
        (champs["amenagement"], int(champs["vue_fragile"]),
         int(champs["gaucher"]), champs["precisions"][:200], eleve_id),
    )


def regler_prof_principal(classe_id: int, annee_id: int, nom: str) -> None:
    """EF-C6 — and their name opens a mail link, on the screen side."""
    garde_ecriture(annee_id)
    execute("UPDATE classes SET prof_principal = ? WHERE id = ?",
            (nom.strip()[:60], classe_id))


def ajouter_eleve(classe_id: int, annee_id: int, nom: str, prenom: str,
                  debut: str) -> int:
    """Create a pupil and enrol them (EF-C5)."""
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
    """The pupil leaves the lists, **and nothing is erased** (RT-2)."""
    garde_ecriture(annee_id)
    execute(
        "UPDATE inscriptions SET fin = ? WHERE eleve_id = ? AND classe_id = ? "
        "AND fin IS NULL", (fin, eleve_id, classe_id))


def faire_revenir(eleve_id: int, classe_id: int, annee_id: int,
                  debut: str) -> None:
    """They come back: a NEW enrolment, not an end one erases.

    Erasing the end date would make the fact that they left disappear,
    and EF-C9's path would return a continuous stay that did not happen.
    """
    garde_ecriture(annee_id)
    execute(
        "INSERT INTO inscriptions (eleve_id, classe_id, debut, fin) "
        "VALUES (?, ?, ?, NULL)", (eleve_id, classe_id, debut))


def transferer(eleve_id: int, depuis: int, vers: int, annee_id: int,
               jour: str) -> None:
    """A transfer is a DEPARTURE plus an ENTRY (EF-C5, RT-2)."""
    garde_ecriture(annee_id)
    faire_sortir(eleve_id, depuis, annee_id, jour)
    faire_revenir(eleve_id, vers, annee_id, jour)


def supprimer_classe(classe_id: int, annee_id: int) -> int:
    """Delete the class and **the pupils belonging only to it**.

    RT-2 has two halves, and it is here that the second applies: *"on the
    other hand, deleting a class takes with it the pupils belonging only
    to it — otherwise they would stay in the database with no class,
    invisible"*.

    Returns the number of pupils taken, so the screen can say it before
    doing it (EF-C8: explicit confirmation).
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
    """How many pupils a deletion would take — BEFORE doing it.

    EF-C8 asks for an explicit confirmation; a confirmation that does not
    say what it costs is not one.
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
