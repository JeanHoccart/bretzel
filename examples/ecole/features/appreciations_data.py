"""features/appreciations_data — data: the observation sheets.

``kind="data"``. It carries EF-E1 to EF-E3 on the data side, and **the
flag that decides everything**: ``ecrite_main``.

EF-E3, in one line of schema
-----------------------------
*"As soon as the teacher writes their own text, the application never
rewrites it again — even if the observations change afterwards. A button
allows explicitly asking for a proposal again."*

Three behaviours, one single flag:

=========================  ======================================
gesture                    what ``ecrite_main`` becomes
=========================  ======================================
tick an observation        unchanged; the text is reproposed
                           **only if it is 0**
write in the field         goes to 1, permanently
click "repropose"          goes back to 0, and the text is redone
=========================  ======================================

Without this flag, the only way of not overwriting would be to compare
the text with what would have been proposed — which fails as soon as the
teacher fixes a comma.
"""

from __future__ import annotations

from bretzel import Feature
from bretzel.state import AppState, field
from examples.ecole.core.db import execute, query
from examples.ecole.core.domain import CRITERES
from examples.ecole.features.annees import garde_ecriture


class FichesRev(AppState):
    """The token the zones watch. Bumped at every write.

    ⚠️ **A database write touches NO typed state**, so the re-render
    engine does not see it. Without this token, ticking a tile writes the
    sheet correctly and **the screen does not move**: no error, no trace,
    the text stays empty and one looks for the bug in the comment
    factory.

    It is ``examples/crm``'s pattern (``ContactsRev``), and it was
    forgotten here until the probe: the previous screens worked by
    accident, because their handlers ALSO mutated a draft
    (``draft.ouvert = False``) and that mutation woke the zone.

    ``merge="add"`` and not an assignment: two simultaneous writes would
    lose an increment, and the token would stop advancing as fast as the
    writes.
    """

    rev: int = field(default=0, merge="add")


def criteres_et_niveaux() -> list[dict]:
    """The four criteria and their levels, in report-card order.

    A single query for the twenty-four levels: four queries would be more
    readable and would cost four file openings per sheet render.
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
    """A pupil's sheet, created on the fly if it does not exist.

    An empty sheet is not an absence of sheet: the term exists, so does
    the pupil, and the screen must be able to tick. Creating it on READ
    avoids a "save first" that would make no sense.
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
    """A class's every comment, for the review (EF-E9)."""
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
    """``criterion → [ticked tints]`` — the summary's input (EF-F)."""
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
    """EF-E5's wording, that of the term asked for.

    Falls back on the long label if the table has nothing: a missing
    sentence must not empty a comment.
    """
    lignes = query(
        "SELECT texte FROM phrases WHERE niveau_critere_id = ? "
        "AND trimestre = ?", (niveau_id, trimestre))
    if lignes:
        return lignes[0]["texte"]
    repli = query("SELECT long FROM niveaux_critere WHERE id = ?",
                  (niveau_id,))
    return repli[0]["long"] if repli else ""


# ── The writes ───────────────────────────────────────────────────────

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
    """Tick (or untick) a level. **At most one per criterion** (EF-E1).

    It is the ``(fiche_id, critere_id)`` primary key that guarantees it,
    not a test here: a rule held by the schema holds whatever the screen.
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
    """Write a proposal — **unless the teacher has written** (EF-E3).

    Returns true if the text was set. The refusal is not an error: it is
    the expected behaviour, and that is why the function returns a
    boolean rather than raising.
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
    """The teacher writes: the flag falls, **permanently**."""
    fiche_id = assurer_fiche(eleve_id, classe_id, trimestre, annee_id)
    execute(
        "UPDATE fiches SET appreciation = ?, ecrite_main = 1 WHERE id = ?",
        (texte[:600], fiche_id))
    FichesRev().rev += 1


def redemander(eleve_id: int, classe_id: int, trimestre: int,
               annee_id: int) -> None:
    """EF-E3's button: *"explicitly ask for a proposal again"*.

    It is the ONLY way of putting ``ecrite_main`` back to zero. Without
    it, one unfortunate correction would condemn the sheet to stay as it
    is until the end of the year.
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
