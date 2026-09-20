"""features/import_data — data: the two-step import, and the archives.

``kind="data"``. EF-J1 to EF-J8 and EF-N1 to EF-N3.

EF-J1 — **one analyses, THEN one validates**
----------------------------------------------
*"Nothing enters the database before the teacher has seen the list — an
import is the only operation that creates three hundred pupils at
once."* Hence two functions and not one: :func:`analyser` touches
nothing, :func:`valider` writes.

EF-J5 — **the matching is done by NAME, never by position**
--------------------------------------------------------------
**Trap no. 5**, and it is the most visible of all: *"one pupil gone over
the summer would be enough to shift all the rest, and to put every face
on its neighbour"*. The comparison covers the surname AND the first name
together, without accents or case (EF-J6) — "courty leane" must find
"COURTY Léane" — and the two fields stay DISTINCT (EF-C7).

EF-J3 — a class that ALREADY has pupils is refused
----------------------------------------------------
*"A second pass would duplicate the whole list there."* A class created
empty by the timetable (EF-B6) is, on the other hand, found by its code
and filled: it is exactly the normal case at the start of term.
"""

from __future__ import annotations

import unicodedata
from datetime import date

from bretzel import Feature
from bretzel.state import AppState, field
from examples.ecole.core.db import execute, query, scalar
from examples.ecole.core.domain import cycle_propose, niveau_du_code
from examples.ecole.features.annees import garde_ecriture


class ImportRev(AppState):
    """The import zones' token. The same reason as the others."""

    rev: int = field(default=0, merge="add")


def sans_accents(texte: str) -> str:
    """A name's comparable form (EF-J6).

    *"The comparison covers the surname AND the first name together,
    without accents or case: 'courty leane' must find 'COURTY Léane'."*
    The two fields stay distinct — it is the caller that brings them
    together, not this function that merges them.
    """
    plie = unicodedata.normalize("NFKD", texte)
    return "".join(c for c in plie if not unicodedata.combining(c)).lower()


def cle_de(nom: str, prenom: str) -> str:
    """The matching key: surname AND first name, never one of the two."""
    return f"{sans_accents(nom.strip())}|{sans_accents(prenom.strip())}"


def lire_csv(texte: str) -> list[dict]:
    """EF-K's drop (out of scope: the BIFF8 `.xls`, § 3.2).

    One row per pupil, ``SURNAME;Firstname`` or ``SURNAME,Firstname``.
    The format is deliberately poor: *"reading the school's .xls measures
    the library, not the framework"*, so the specification replaces it
    with a CSV drop.

    ⚠️ What is NOT recognised is returned as is (EF-J7): *"a name absent
    from the class, two homonyms, a pupil with no photo are returned as
    they are, on screen, so the teacher decides"*. So an unreadable row
    becomes a row in error, not a row skipped.
    """
    lignes: list[dict] = []
    for numero, brute in enumerate(texte.splitlines(), start=1):
        ligne = brute.strip()
        if not ligne or ligne.lower().startswith(("nom;", "nom,")):
            continue
        morceaux = [m.strip() for m in ligne.replace(",", ";").split(";")]
        morceaux = [m for m in morceaux if m]
        if len(morceaux) < 2:
            lignes.append({"ligne": numero, "brut": ligne, "nom": "",
                           "prenom": "", "erreur": "nom et prénom attendus"})
            continue
        lignes.append({"ligne": numero, "brut": ligne, "nom": morceaux[0],
                       "prenom": morceaux[1], "erreur": ""})
    return lignes


def analyser(annee_id: int, code: str, texte: str) -> dict:
    """EF-J1 — **the first step: one looks, one writes nothing.**

    Returns ``{classe, refus, lignes, doublons, connus, inconnus}``. No
    write, no exception: the screen must be able to show everything,
    including what is wrong.
    """
    code = code.strip()
    classes = query(
        "SELECT id, code, libelle FROM classes WHERE annee_id = ? AND code = ?",
        (annee_id, code))
    classe = classes[0] if classes else None

    refus = ""
    if not code:
        refus = "Il faut un code de classe."
    elif classe is not None:
        effectif = scalar(
            "SELECT COUNT(*) FROM inscriptions WHERE classe_id = ? "
            "AND fin IS NULL", (classe["id"],)) or 0
        if effectif:
            # EF-J3: *"a second pass would duplicate the whole list
            # there"*.
            refus = (f"{code} a déjà {effectif} élèves. Un second import y "
                     f"dupliquerait la liste entière. Pour remplacer les "
                     f"photos, c'est le bouton séparé.")

    lignes = lire_csv(texte)
    vues: dict[str, int] = {}
    for ligne in lignes:
        if ligne["erreur"]:
            continue
        cle = cle_de(ligne["nom"], ligne["prenom"])
        vues[cle] = vues.get(cle, 0) + 1
    for ligne in lignes:
        if not ligne["erreur"] and vues[cle_de(ligne["nom"],
                                               ligne["prenom"])] > 1:
            # EF-J7: two homonyms are SAID, not decided at random.
            ligne["erreur"] = "en double dans le fichier"

    deja = deja_en_base(annee_id) if classe is None else {}
    for ligne in lignes:
        cle = cle_de(ligne["nom"], ligne["prenom"])
        ligne["connu"] = deja.get(cle, "")

    return {
        "classe": classe,
        "code": code,
        "refus": refus,
        "lignes": lignes,
        "valides": [li for li in lignes if not li["erreur"]],
        "erreurs": [li for li in lignes if li["erreur"]],
    }


def deja_en_base(annee_id: int) -> dict[str, str]:
    """``key → class code`` for the pupils already enrolled this year.

    Serves to SAY that a name in the file is already elsewhere (EF-J7),
    not to discard it: it is the teacher who decides.
    """
    return {
        cle_de(r["nom"], r["prenom"]): r["code"]
        for r in query(
            """
            SELECT e.nom, e.prenom, c.code
            FROM inscriptions i JOIN eleves e ON e.id = i.eleve_id
            JOIN classes c ON c.id = i.classe_id
            WHERE c.annee_id = ? AND i.fin IS NULL
            """,
            (annee_id,))
    }


def valider(annee_id: int, code: str, lignes: list[dict]) -> int:
    """EF-J1 — **the second step: now one writes.**

    An absent class is CREATED (the start-of-term case); a class created
    empty by the timetable is found by its code and filled (EF-J3).
    Returns the number of pupils added.
    """
    garde_ecriture(annee_id)
    classes = query(
        "SELECT id FROM classes WHERE annee_id = ? AND code = ?",
        (annee_id, code))
    if classes:
        classe_id = classes[0]["id"]
    else:
        niveau = niveau_du_code(code)
        classe_id = execute(
            "INSERT INTO classes (annee_id, code, libelle, cycle, niveau, "
            "rang) VALUES (?, ?, ?, ?, ?, 0)",
            (annee_id, code, code, cycle_propose(niveau), niveau))

    debut = query("SELECT debut FROM annees WHERE id = ?",
                  (annee_id,))[0]["debut"]
    ajoutes = 0
    for ligne in lignes:
        if ligne.get("erreur"):
            continue
        eleve_id = execute(
            "INSERT INTO eleves (nom, prenom) VALUES (?, ?)",
            (ligne["nom"][:60], ligne["prenom"][:60]))
        execute(
            "INSERT INTO inscriptions (eleve_id, classe_id, debut, fin) "
            "VALUES (?, ?, ?, NULL)", (eleve_id, classe_id, debut))
        ajoutes += 1
    ImportRev().rev += 1
    return ajoutes


def apparier_photos(annee_id: int, classe_id: int,
                    lignes: list[dict]) -> dict:
    """EF-J4, EF-J5 — **replace the photos, without touching the class.**

    *""Remplacer les photos" is a button SEPARATE from "Ajouter les
    élèves". We above all do not want to create thirty duplicates while
    thinking we are refreshing photos."* So this function creates NO
    pupil and removes none: it matches by NAME and sets the images.

    Returns ``{poses, absents}`` — and the absent ones are SAID (EF-J7).
    """
    garde_ecriture(annee_id)
    en_classe = {
        cle_de(r["nom"], r["prenom"]): r["id"]
        for r in query(
            """
            SELECT e.id, e.nom, e.prenom FROM inscriptions i
            JOIN eleves e ON e.id = i.eleve_id
            WHERE i.classe_id = ? AND i.fin IS NULL
            """,
            (classe_id,))
    }
    poses, absents = 0, []
    for ligne in lignes:
        if ligne.get("erreur"):
            continue
        eleve_id = en_classe.get(cle_de(ligne["nom"], ligne["prenom"]))
        if eleve_id is None:
            absents.append(f"{ligne['nom']} {ligne['prenom']}")
            continue
        # EF-J8: the cropping is a TRANSFORMATION, not a replacement —
        # the original image is kept. Here the demonstration set carries
        # only initials (§ 12), so we record the cropping's STATE rather
        # than a file: it is that state the screen distinguishes.
        execute("UPDATE eleves SET photo = ? WHERE id = ?",
                ("cadrage-par-defaut", eleve_id))
        poses += 1
    ImportRev().rev += 1
    return {"poses": poses, "absents": absents}


# ── The archives (EF-N) ──────────────────────────────────────────────

def archive_de(classe_id: int) -> dict:
    """EF-N1 — *"everything is there, in the order one looks for it"*.

    Photo board, marks for all THREE terms, comments, summary. A single
    read, because the archive is produced in one go (EF-N3) and a page
    per term would require three passes.
    """
    classes = query(
        "SELECT c.id, c.code, c.libelle, c.cycle, c.prof_principal, "
        "a.libelle AS annee FROM classes c JOIN annees a ON a.id = c.annee_id "
        "WHERE c.id = ?", (classe_id,))
    if not classes:
        return {}
    eleves = query(
        """
        SELECT e.id, e.nom, e.prenom FROM inscriptions i
        JOIN eleves e ON e.id = i.eleve_id
        WHERE i.classe_id = ?
        ORDER BY e.nom COLLATE NOCASE, e.prenom COLLATE NOCASE
        """,
        (classe_id,),
    )
    notes = query(
        """
        SELECT n.eleve_id, ev.trimestre, ev.nom, ev.bareme, ev.coefficient,
               n.absent, n.valeur
        FROM notes n JOIN evaluations ev ON ev.id = n.evaluation_id
        WHERE ev.classe_id = ? ORDER BY ev.trimestre, ev.date
        """,
        (classe_id,),
    )
    appreciations = query(
        "SELECT eleve_id, trimestre, appreciation FROM fiches "
        "WHERE classe_id = ? AND appreciation <> ''", (classe_id,))
    return {"classe": classes[0], "eleves": eleves, "notes": notes,
            "appreciations": appreciations}


def classes_archivables(annee_id: int) -> list[dict]:
    return query(
        "SELECT id, code, libelle FROM classes WHERE annee_id = ? "
        "ORDER BY rang, code", (annee_id,))


def photo_datee() -> str:
    """Today's date, for an archive's header (EF-N2).

    *"It is an ARCHIVE, not a report card: it must be re-readable in ten
    years without the program that produced it."* An archive without its
    production date does not situate itself.
    """
    return date.today().isoformat()


feature = Feature(
    name="import_data",
    kind="data",
    provides=[
        ImportRev, sans_accents, cle_de, lire_csv, analyser, deja_en_base,
        valider, apparier_photos, archive_de, classes_archivables,
        photo_datee,
    ],
    uses=["db", "annees"],
)
