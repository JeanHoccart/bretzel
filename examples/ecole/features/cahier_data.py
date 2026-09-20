"""features/cahier_data — data: the lesson log, the progression, the
sheets.

``kind="data"``. EF-K1 to EF-K12, EF-L1 to EF-L3, EF-M1 to EF-M4.

EF-K2 — **the gesture aimed at is the evening one**
-----------------------------------------------------
*"Open, check, copy onto École Directe. All the rest is there to save
typing."* Five pre-fillings, and the fifth is the only one that cannot be
guessed:

1. the class OF THE MOMENT, from the timetable;
2. the chapter of that class's last session;
3. the NEXT session, for that class;
4. the text pre-filled with both titles;
5. **the chapter is announced only once per class.** *"Repeated at every
   session, it would drown the day's title on École Directe."*

EF-K5 — the log reads the GRID **and** the exceptions
-------------------------------------------------------
*"Never the grid alone — otherwise it would offer to record a class that
did not take place."* That is why :func:`prochaines_heures` goes through
``grille_data.semaine_affichee``, which already mixes the three sources,
instead of re-reading ``creneaux``.

EF-M3 — a sheet is attached by TITLE, never by number
-------------------------------------------------------
**Trap no. 10.** *"A number slips as soon as a session is inserted
mid-year: every following sheet would end up on its neighbour, with
nothing to say so."* So ``fiches_seance``'s key is ``(chapitre_id,
seance_titre)``, and the number is only a position of the day.
"""

from __future__ import annotations

from datetime import date, timedelta

from bretzel import Feature
from bretzel.state import AppState, field
from examples.ecole.core.db import execute, query
from examples.ecole.core.domain import est_un_tp, niveau_du_code
from examples.ecole.features.annees import garde_ecriture


class CahierRev(AppState):
    """The log zones' token. The same reason as the others."""

    rev: int = field(default=0, merge="add")


def entrees_de(classe_id: int, croissant: bool = False) -> list[dict]:
    """A class's entries (EF-K8).

    *"A class's list is read with the day's session at the head. The
    archive, for its part, is read in increasing chronological order,
    September at the top. It is not the same object: a screen is
    consulted, an archive is read from beginning to end."* Hence the
    parameter, and its default.
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
    """A level's chapters (EF-L3).

    *"The level brings a class close to a chapter through the start of
    its code."* The matching goes through
    :func:`~examples.ecole.core.domain.niveau_du_code`, which is the only
    way of doing it in the whole application.
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
    """EF-K11 — *"nothing is proposed if the class has already recorded
    this session: that would be inviting them to write it twice"*."""
    return bool(query(
        "SELECT 1 FROM cahier WHERE classe_id = ? AND chapitre_id = ? "
        "AND seance_titre = ? LIMIT 1", (classe_id, chapitre_id, titre)))


def chapitre_deja_annonce(classe_id: int, chapitre_id: int) -> bool:
    """EF-K2 § 5 — **the chapter is announced only once per class.**

    *"Repeated at every session, it would drown the day's title on École
    Directe."* And it is PER CLASS, which is the reason why picking up an
    entry for a sister class moves that line and nothing else (EF-K9).
    """
    return bool(query(
        "SELECT 1 FROM cahier WHERE classe_id = ? AND chapitre_id = ? LIMIT 1",
        (classe_id, chapitre_id)))


def proposition(classe_id: int, niveau: str) -> dict:
    """What the evening form must already carry (EF-K2).

    Returns ``{chapitre_id, chapitre, numero, titre, contenu, travail}``.
    The four pre-fillings read in the specification's order; the fifth —
    the chapter announcement — is the ``contenu``'s conditional line.
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
        # The chapter is finished for this class: we move to the next.
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
    """EF-K10 — *"what a sister class recorded for the same session"*.

    *"The gesture: we are on 4e2, we look for what 4e1 did. Without it
    one has to go to 4e1, find the session and push it — the opposite of
    the direction one thinks in."*

    Nothing is returned if THIS class has already recorded the session
    (EF-K11).
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
    """EF-K9 — *"the text is ADJUSTED, never recomputed"*.

    *"A first version recomposed it from the chapter, and therefore threw
    away everything written by hand — which is exactly what one wants to
    pick up. Only the chapter-announcement line moves, because the rule
    'the chapter is announced only once' is PER CLASS."*

    So: we remove the announcement if it is there and should not be, we
    add it if it should be. The rest of the text is never touched.
    """
    lignes = contenu.split("\n")
    annonce = f"{chapitre}."
    portait = bool(lignes) and lignes[0].strip() == annonce
    corps = lignes[1:] if portait else lignes
    if annoncer:
        return "\n".join([annonce, *corps])
    return "\n".join(corps).lstrip("\n")


def prochaines_heures(annee: dict, depuis: date, jours: int = 7) -> list[dict]:
    """The hours coming up, **grid AND exceptions** (EF-K5, EF-K6,
    EF-K7).

    - a CANCELLED hour is not there, and is no longer proposed as the
      next lesson (EF-K5);
    - a holiday day is not there either (EF-K6: *"the log never offers
      homework for Monday 26 October if that Monday falls in the
      holidays"*);
    - an hour with a NATURE has no session to record (EF-K7).

    And every hour says whether it is a **three-hour practical**
    (EF-K12), by ``domain.est_un_tp``'s single rule: *"one single
    definition of the practical in the whole application, never two"*.
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
    """EF-L1 — **a table, not a list.**

    *"One row per class, one column per chapter, and in each cell where
    it has got to."* The need behind it: *"five classes on the same
    syllabus drift apart without anybody noticing, and one discovers it
    in June when it is too late"* — so the gap must read COLUMN BY
    COLUMN, not by reading five logs one after the other.
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


# ── The session sheets (EF-M) ────────────────────────────────────────

def fiche_seance(chapitre_id: int, titre: str) -> dict | None:
    """A session's sheet, **by its TITLE** (EF-M3, trap no. 10)."""
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
    """A chapter's sheets, indexed by session TITLE."""
    return {
        r["seance_titre"]: {"id": r["id"], "resume": r["resume"]}
        for r in query(
            "SELECT id, seance_titre, resume FROM fiches_seance "
            "WHERE chapitre_id = ?", (chapitre_id,))
    }


def fiches_orphelines(chapitre_id: int) -> list[str]:
    """EF-M4 — those that could not be reattached, **flagged**.

    *"A session renamed, inserted or deleted must leave the sheets where
    they belong, and FLAG those that could not be reattached rather than
    putting them somewhere at random."* So a sheet whose title matches no
    session of the chapter is said, not reassigned — reassigning it at
    random is precisely trap no. 10.
    """
    titres = {s["titre"] for s in seances_de(chapitre_id)}
    return [t for t in fiches_du_chapitre(chapitre_id) if t not in titres]


# ── The writes ───────────────────────────────────────────────────────

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
    """EF-K4 — like the marks (EF-D7), with the date."""
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
    """EF-M2 — the summary is REWRITTEN. It is the half one corrects."""
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
    """EF-M2 — the two notebooks one ADDS to.

    *"Every note is dated and DOES NOT REPLACE the previous one: the same
    session given to 3e2 then to 3e9 makes two observations."* It is an
    ``INSERT``, never an ``UPDATE``, and that is the whole difference
    with the summary just above.
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
