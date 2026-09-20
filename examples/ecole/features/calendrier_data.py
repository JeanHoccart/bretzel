"""features/calendrier_data — data: the year, its terms, its periods.

``kind="data"``: no page. It carries the calendar's reads and **the six
writes guarded by RT-1** — each begins with
:func:`~examples.ecole.features.annees.garde_ecriture`, and it is the
only reason a page can settle for not showing a button (EF-C10): the
refusal exists underneath.

What it computes and nobody else must recompute
------------------------------------------------
:func:`cours_perdus` is EF-A11's answer, and it has **three distinct
forms** that must above all not be confused:

==================  ===================================================
what it returns     what it means
==================  ===================================================
``None``            the alternation is undetermined — no week-A
                    reference date. We do **not** return "no lesson":
                    we do not know (RT-4)
``[]``              the list is EMPTY, and it is the good news: that
                    day there was no lesson to lose
``[(code, n), …]``  what it costs, the class most affected first
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
    """The day's eight boundaries, in order (EF-B3)."""
    return query(
        "SELECT id, rang, debut, fin FROM horaires "
        "WHERE annee_id = ? ORDER BY rang",
        (annee_id,),
    )


def trimestres_de(annee_id: int) -> dict[tuple[str, int], str]:
    """``(cycle, number) → end``, and nothing for the empty cells.

    A dict rather than a list: the screen asks for six named cells
    (EF-A3), and a missing cell must read as missing — not as a row to
    find in a list.
    """
    return {
        (r["cycle"], r["numero"]): r["fin"] or ""
        for r in query(
            "SELECT cycle, numero, fin FROM trimestres WHERE annee_id = ?",
            (annee_id,),
        )
    }


def periodes_de(annee_id: int) -> list[dict]:
    """The periods without class, **in the year's order** (EF-A6).

    *"Ordering by category — the four holidays first — put the staff day
    of 16 October under Easter"*: it is trap no. 13, and it is closed
    here, in the ``ORDER BY``, not in the screen.
    """
    return query(
        "SELECT id, libelle, debut, fin FROM vacances "
        "WHERE annee_id = ? ORDER BY debut, fin",
        (annee_id,),
    )


def cours_perdus(
    annee: dict, debut: date, fin: date
) -> list[tuple[str, int]] | None:
    """What a period makes one lose in hours (EF-A11).

    ⚠️ **Goes through :func:`~examples.ecole.core.domain.semaine_ab`,
    never through a week number.** It is trap no. 2: counted on ISO
    numbers, the count attributes the hours to the wrong week from
    January on, one year in five. The only place the alternation is
    computed in the app is that domain function.

    Sunday is skipped; Saturday is not, the grid runs that far.
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
    # The most affected first, then the code — without the second
    # criterion, two classes on a tie would swap places from one render
    # to the next.
    return sorted(compte.items(), key=lambda paire: (-paire[1], paire[0]))


# ── The writes. Each opens on the RT-1 guard ──────────────────────────

def modifier_annee(annee_id: int, champs: dict[str, str]) -> None:
    """Correct the label, the start, the end, the reference (EF-A1)."""
    garde_ecriture(annee_id)
    execute(
        "UPDATE annees SET libelle = ?, debut = ?, fin = ?, lundi_ref = ? "
        "WHERE id = ?",
        (champs["libelle"], champs["debut"], champs["fin"],
         champs["lundi_ref"] or None, annee_id),
    )


def creer_annee(libelle: str, debut: str, fin: str) -> int:
    """Create a new year, **in consultation mode** (EF-A2).

    No RT-1 guard here, and it is not an oversight: creating a year
    writes into none. The new one is born out of service — it is
    :func:`designer_en_cours` that puts it into service, and it is a
    second gesture on purpose. A year that became "current" at its
    creation would switch every screen to an empty database.
    """
    return execute(
        "INSERT INTO annees (libelle, debut, fin, en_cours, lundi_ref) "
        "VALUES (?, ?, ?, 0, NULL)",
        (libelle, debut, fin),
    )


def designer_en_cours(annee_id: int) -> None:
    """Switch the year into service. **Only one at a time** (§ 5.1).

    No RT-1 guard: it is the operation that MOVES the barrier, it cannot
    be behind it. The two writes are done in this order — one switches
    off before switching on — so no intermediate instant has two current
    years.
    """
    execute("UPDATE annees SET en_cours = 0 WHERE en_cours = 1")
    execute("UPDATE annees SET en_cours = 1 WHERE id = ?", (annee_id,))


def poser_trimestre(annee_id: int, cycle: str, numero: int, fin: str) -> None:
    """Set (or clear) a term's END (EF-A3).

    The start is never entered: it reads as the day after the previous
    one. An empty end clears the row rather than writing an empty string
    — an empty cell must read as empty everywhere, including in the
    database.
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
    """Set, correct or CLEAR a period without class (EF-A5).

    The specification's three rules, in the order they read:

    - an **empty start clears** the period. It is the way of removing a
      row without one more button, and it is the one the teacher knows;
    - an **empty end equals the start**: a public holiday is entered with
      a single date, and it comes out with its two identical dates
      (EF-A8);
    - the name is the key, because zone B's four holidays are PROPOSED
      and are filled in by their name (EF-A4).
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
    """Remove a period. The explicit counterpart of the "empty start"."""
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
