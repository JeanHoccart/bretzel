"""kanban/donnees — the demonstration board, isolated per visitor.

``SessionState`` keeps the cards and the history in the browser's signed
session. Two visitors can therefore neither read nor modify each other's
data; the demo keeps its full behaviour inside each session.

No database: restarting the server puts the board back to its starting
state. Two other demos (``crm``, ``mad``) show SQLite; here the source of
truth fits in memory, and that is what makes the demonstration readable
in one file.

⚠️ **The seed's identifiers are WRITTEN, never drawn at random.** A
``default_factory`` on a server state is re-evaluated at every request as
long as no mutation has persisted it: a ``uuid4`` here would mint fresh
identifiers at every render, and the first drag would aim at a card that
already no longer exists.

**The order inside a column is a floating ``rang``**, not the position in
the list. Dropping between two cards takes the midpoint of their two
ranks, so a single card is rewritten — and that is what makes
``annuler`` trivial: restoring one card is enough, no neighbour has
moved. The price is written down: after thirty-odd drops at the same
spot, the floats have no midpoint left to offer. A real app renumbers;
a demo board has no time for that.
"""

from __future__ import annotations

import time
from datetime import date, timedelta
from typing import Any

from bretzel import Feature, t
from bretzel.state import SessionState, field

#: The columns, in board order, with their **work-in-progress limit**.
#: ``None`` = no limit. The limit is a rule of the board, not a
#: decoration: it refuses a drop, and the server is what arbitrates.
#:
#: The key and the limit are language-free, so they stay constants; the
#: LABEL is not, so it lives in :func:`colonnes` — a function, because
#: :func:`~examples.kanban.core.i18n.tr` reads the request's language and
#: a module constant is evaluated once at import.
CLES: tuple[str, ...] = ("a_faire", "en_cours", "en_revue", "fini")
LIMITES: dict[str, int | None] = {
    "a_faire": None, "en_cours": 3, "en_revue": 2, "fini": None,
}


#: Each column's status mark: a lucide icon and the colour that paints
#: it. The shapes follow the usual tracker reading — empty, half full,
#: dotted, ticked — so the four columns say where a card stands before
#: their labels are read.
STATUTS: dict[str, tuple[str, str]] = {
    "a_faire": ("circle-dashed", "muted"),
    "en_cours": ("contrast", "warning"),
    "en_revue": ("circle-dot", "primary"),
    "fini": ("circle-check", "success"),
}


def colonnes() -> tuple[tuple[str, str, int | None], ...]:
    """``(key, label, limit)`` per column, in board order."""
    return (
        ("a_faire", t("To do"), None),
        ("en_cours", t("In progress"), 3),
        ("en_revue", t("In review"), 2),
        ("fini", t("Done"), None),
    )


def libelles() -> dict[str, str]:
    """``key -> label`` for the columns, in the request's language."""
    return {cle: lib for cle, lib, _ in colonnes()}

#: The team. The key serves as session identity ("you are…") and as a
#: card's assignee — two roles for one table, because it is the same
#: person.
#:
#: The colours are the four hues ``core/theme.py`` adds to the palette,
#: not semantic slots: a person is not a status, and the semantic
#: colours already paint the labels (:data:`ETIQUETTES`).
MEMBRES: tuple[tuple[str, str, str, str], ...] = (
    ("cam", "Camille Roux", "CR", "berry"),
    ("sam", "Samuel Diallo", "SD", "ocean"),
    ("noa", "Noa Berger", "NB", "ember"),
    ("lea", "Léa Marchand", "LM", "pine"),
)

NOMS: dict[str, str] = {cle: nom for cle, nom, _, _ in MEMBRES}
INITIALES: dict[str, str] = {cle: ini for cle, _, ini, _ in MEMBRES}
COULEURS: dict[str, str] = {cle: coul for cle, _, _, coul in MEMBRES}

#: The available labels, with the semantic colour that renders them.
ETIQUETTES: tuple[tuple[str, str, str], ...] = (
    ("bug", "Bug", "error"),
    ("ux", "UX", "info"),
    ("perf", "Perf", "warning"),
    ("doc", "Doc", "muted"),
    ("infra", "Infra", "success"),
)

LIB_ETIQUETTE: dict[str, str] = {cle: lib for cle, lib, _ in ETIQUETTES}
COUL_ETIQUETTE: dict[str, str] = {cle: coul for cle, _, coul in ETIQUETTES}


def tache(
    ident: str,
    colonne: str,
    titre: str,
    qui: str,
    etiquettes: tuple[str, ...] = (),
    echeance: str = "",
    points: int = 0,
    description: str = "",
    sous_taches: tuple[tuple[str, bool], ...] = (),
    commentaires: tuple[tuple[str, str], ...] = (),
) -> dict[str, Any]:
    """A complete card, with its defaults. The ``rang`` comes after.

    The seeded comments are dated a few hours back, the last one the
    most recent, so the thread reads as a conversation that happened.

    ⚠️ Counted back from today's MIDNIGHT, not from the clock. The seed
    is a ``default_factory``, rebuilt at every request until the first
    write persists the board: a value that moved between two builds
    would make the framework see a change nobody made, and re-render the
    whole board on a visitor's first click.
    """
    minuit = time.mktime(date.today().timetuple())
    return {
        "id": ident,
        "colonne": colonne,
        "titre": titre,
        "qui": qui,
        "etiquettes": list(etiquettes),
        "echeance": echeance,
        "points": points,
        "description": description,
        "sous_taches": [{"texte": t, "fait": f} for t, f in sous_taches],
        "commentaires": [
            {"qui": q, "texte": t,
             "t": minuit - 4 * 3600 * (len(commentaires) - i)}
            for i, (q, t) in enumerate(commentaires)
        ],
        "rang": 0.0,
    }


def dans(jours: int) -> str:
    """The ISO date ``jours`` days from today — the seed's due dates.

    Relative, so the public demo never shows a sprint whose every
    deadline went by months ago: one card is a day late, one is due
    today, the rest spread over the coming weeks.
    """
    return (date.today() + timedelta(days=jours)).isoformat()


#: The seed, column by column and in display order. What a real team
#: sprint produces: enough material for the board to overflow vertically,
#: which is the only way to see a column scroll.
#:
#: A FUNCTION and no longer a constant: every sentence goes through
#: :func:`~examples.kanban.core.i18n.tr`, which reads the request's
#: language. ``semer`` is called from a ``default_factory`` on a
#: ``SessionState``, hence inside a render context — the seed is
#: therefore in the language of whoever first opens the board.
def graine() -> tuple[dict[str, Any], ...]:
    """The fifteen seeded cards, in the request's language."""
    return (
        tache(
            "c01", "a_faire",
            t("Sign-in screen: forgotten password"),
            "sam", ("ux",), dans(9), 3,
            t("The link exists but returns a 404 since the routing was "
               "reworked. To be rewired onto the new single-use token "
               "flow."),
            ((t("Rewire the route"), False),
             (t("Email template"), False),
             (t("30-minute expiry"), False)),
        ),
        tache(
            "c02", "a_faire",
            t("Audit log exportable as CSV"),
            "noa", ("infra", "doc"), dans(14), 5,
            t("The large accounts ask for it for their internal audits. "
               "One row per action, the export runs as a background task."),
            ((t("Paginated query"), False),
             (t("Writing the file"), False),
             (t("Button and notification"), False),
             (t("Document the format"), False)),
        ),
        tache(
            "c03", "a_faire",
            t("Fix the VAT computation on credit notes"),
            "lea", ("bug",), dans(2), 2,
            t("A credit note issued after a rate change applies the day\'s "
               "rate, not the original invoice\'s."),
            ((t("Reproduce on real data"),
              True),
             (t("Fix"), False)),
            (("cam", t("Reported by two clients this week, to be "
                        "prioritised.")),),
        ),
        tache(
            "c04", "a_faire",
            t("Rework the pricing page"),
            "cam", ("ux",), "", 8,
            t("Three plans instead of five, and the comparison goes below "
               "the fold. Mock-ups approved, the integration is left."),
        ),
        tache(
            "c05", "a_faire",
            t("Drop the moment.js dependency"),
            "noa", ("perf",), "", 3,
            t("68 kB to format three dates. Native formatting is enough "
               "now that the old browsers are no longer supported."),
        ),
        tache(
            "c06", "a_faire",
            t("A ten-minute getting-started guide"),
            "sam", ("doc",), dans(21), 5,
            t("The sign-up drop-off rate is decided in the first five "
               "minutes. A written walkthrough, tested on three people."),
        ),
        tache(
            "c07", "en_cours",
            t("Merge duplicate accounts"),
            "lea", ("bug", "infra"), dans(1), 8,
            t("Two accounts created with the same address in upper and in "
               "lower case. They must be merged without losing the "
               "history."),
            ((t("Duplicate detection"), True),
             (t("Merge screen"), True),
             (t("Replaying the history"), False)),
            (("noa", t("The detection runs, 412 pairs found in the "
                        "database.")),
             ("lea", t("I am taking the merge screen, ready tomorrow."))),
        ),
        tache(
            "c08", "en_cours",
            t("Dashboard caching"),
            "noa", ("perf",), dans(-1), 5,
            t("The dashboard recomputes twelve aggregates at every load. A "
               "five-minute cache is enough, invalidated on write."),
            ((t("Choosing the cache key"), True),
             (t("Invalidation"), False)),
        ),
        tache(
            "c09", "en_cours",
            t("Date picker accessibility"),
            "cam", ("ux", "bug"), dans(4), 3,
            t("The calendar cannot be reached from the keyboard, and the "
               "screen reader announces \"button\" without saying which "
               "date."),
            ((t("Tab order"), True),
             (t("ARIA labels"), False),
             (t("Screen-reader test"), False)),
        ),
        tache(
            "c10", "en_revue",
            t("Rate limiting on the public API"),
            "sam", ("infra",), dans(0), 5,
            t("A hundred requests per minute per token, with the standard "
               "headers so the clients know where they stand."),
            ((t("In-memory counter"), True),
             (t("Quota headers"), True),
             (t("Documentation"), True)),
            (("cam", t("Reviewed, only the expired-token case is missing.")),),
        ),
        tache(
            "c11", "en_revue",
            t("Spanish translation of the interface"),
            "lea", ("doc", "ux"), "", 8,
            t("1 240 strings reviewed by a native translator. The "
               "overflows on long labels are left to check."),
            ((t("Extracting the strings"), True),
             (t("Review"), True),
             (t("Check the overflows"), False)),
        ),
        tache(
            "c12", "fini",
            t("Migration to the new billing engine"),
            "noa", ("infra",), "", 13,
            t("Switched over on a Sunday morning, no visible outage. The "
               "old engine stays readable read-only until December."),
            ((t("Dual writing"), True),
             (t("Switch over"), True),
             (t("Clean-up"), True)),
        ),
        tache(
            "c13", "fini",
            t("Sign in with Google and Microsoft"),
            "cam", ("infra", "ux"), "", 8,
            t("Both providers wired, the existing account is attached by "
               "the verified address."),
            ((t("Google"), True),
             (t("Microsoft"), True),
             (t("Attaching"), True)),
        ),
        tache(
            "c14", "fini",
            t("Fix the PDF export truncated beyond 40 pages"),
            "sam", ("bug",), "", 3,
            t("The generator cut off at the fortieth page without a word. "
               "The buffer was flushed too early."),
            ((t("Reproduce"), True),
             (t("Fix"), True),
             (t("Regression test"), True)),
        ),
        tache(
            "c15", "fini",
            t("Cookie consent banner"),
            "lea", ("doc",), "", 2,
            t("Refused by default, no tracker before the click. Approved "
               "by the firm."),
        ),
    )


def copie(carte: dict[str, Any]) -> dict[str, Any]:
    """A card detached from the original, nested lists included.

    ⚠️ ``{**carte}`` is NOT enough: the three lists would stay shared, so
    the journal's "before" snapshot would change at the same time as the
    card it is supposed to keep — and undoing would give nothing back.
    """
    return {
        **carte,
        "etiquettes": list(carte["etiquettes"]),
        "sous_taches": [dict(s) for s in carte["sous_taches"]],
        "commentaires": [dict(c) for c in carte["commentaires"]],
    }


def semer() -> list[dict[str, Any]]:
    """The seed, with a rank assigned BY POSITION in its column.

    The ranks start at 1, 2, 3… so there is always a free midpoint
    between two neighbours for the first drops.
    """
    compteurs: dict[str, float] = dict.fromkeys(CLES, 0.0)
    cartes: list[dict[str, Any]] = []
    for modele in graine():
        carte = copie(modele)
        compteurs[carte["colonne"]] += 1.0
        carte["rang"] = compteurs[carte["colonne"]]
        cartes.append(carte)
    return cartes


class Tableau(SessionState):
    """The board: its cards, and the story of what happened to them.

    ``journal`` + ``curseur`` form a classic undo stack: the cursor
    counts the APPLIED entries, undo moves it back, redo forward, and a
    new action truncates everything that followed. Each entry carries the
    card BEFORE and AFTER — restoring a dictionary is enough, there is no
    movement to replay backwards.

    The history belongs to the session that created the card: undo and
    redo never act on another visitor's work.
    """

    cartes: list[dict[str, Any]] = field(default_factory=semer)
    journal: list[dict[str, Any]] = field(default_factory=list)
    curseur: int = field(default=0)


def carte_par_id(ident: str) -> dict[str, Any] | None:
    """The card carrying this identifier, or ``None``."""
    for carte in Tableau().cartes:
        if carte["id"] == ident:
            return carte
    return None


def correspond(carte: dict[str, Any], qui: str, etiquette: str,
               texte: str) -> bool:
    """Does this card survive the banner's three filters?"""
    if qui != "tous" and carte["qui"] != qui:
        return False
    if etiquette != "toutes" and etiquette not in carte["etiquettes"]:
        return False
    if texte:
        cible = (carte["titre"] + " " + carte["description"]).casefold()
        if texte.casefold() not in cible:
            return False
    return True


def colonne_de(cle: str, qui: str = "tous", etiquette: str = "toutes",
               texte: str = "") -> list[dict[str, Any]]:
    """A column's VISIBLE cards, in rank order.

    The filters are applied here, so the same function serves the
    rendering and the computation of a drop's neighbours. Letting them
    diverge would amount to inserting a card between two neighbours the
    reader could not see.
    """
    return sorted(
        (c for c in Tableau().cartes
         if c["colonne"] == cle and correspond(c, qui, etiquette, texte)),
        key=lambda c: c["rang"],
    )


def rang_en_tete(cle: str) -> float:
    """The rank that puts a card above every other in ``cle``."""
    premieres = colonne_de(cle)
    return entre(None, premieres[0]["rang"] if premieres else None)


def occupation(cle: str) -> int:
    """How many cards are IN the column — filters excluded.

    A work-in-progress limit counts real work, not what a filter lets you
    see. Hiding somebody else's cards does not free a slot.
    """
    return sum(1 for c in Tableau().cartes if c["colonne"] == cle)


def pleine(cle: str) -> bool:
    """Does the column refuse one more card?"""
    limite = LIMITES.get(cle)
    return limite is not None and occupation(cle) >= limite


def avancement(carte: dict[str, Any]) -> tuple[int, int]:
    """Subtasks done, subtasks in total."""
    sous = carte["sous_taches"]
    return sum(1 for s in sous if s["fait"]), len(sous)


def entre(avant: float | None, apres: float | None) -> float:
    """A free rank between two neighbours, either of which may be absent."""
    if avant is None and apres is None:
        return 1.0
    if avant is None:
        return float(apres) - 1.0  # type: ignore[arg-type]
    if apres is None:
        return float(avant) + 1.0
    return (float(avant) + float(apres)) / 2.0


def depuis(instant: float) -> str:
    """"12 s ago" — derived at display time, never stored.

    A date written into the state would be wrong the second after, and it
    is exactly the kind of field one forgets to update when a new write
    arrives.
    """
    if not instant:
        return ""
    ecart = max(0, int(time.time() - instant))
    if ecart < 60:
        return t("{ecart} s ago", ecart=ecart)
    if ecart < 3600:
        return t("{n} min ago", n=ecart // 60)
    if ecart < 86400:
        return t("{n} h ago", n=ecart // 3600)
    return t("{n} d ago", n=ecart // 86400)


def mois() -> tuple[str, ...]:
    """The months, short, in the request's language: a function, ``t()``
    reads the request."""
    return (t("Jan"), t("Feb"), t("Mar"), t("Apr"), t("May"), t("Jun"),
            t("Jul"), t("Aug"), t("Sep"), t("Oct"), t("Nov"), t("Dec"))


def echeance(carte: dict[str, Any]) -> tuple[str, str]:
    """A card's due date as it reads on the board: ``(label, colour)``.

    Near dates are said in words — ``Today``, ``Tomorrow``,
    ``Yesterday`` — because that is how a team speaks of them; further
    out, ``Oct 3``. The colour says late (``error``), close (``warning``,
    two days or less) or calm; a finished card is never late, its date is
    history. No date, or a malformed one, gives ``("", "muted")``.
    """
    try:
        jour = date.fromisoformat(carte["echeance"])
    except ValueError:
        return "", "muted"
    ecart = (jour - date.today()).days
    if ecart == 0:
        libelle = t("Today")
    elif ecart == 1:
        libelle = t("Tomorrow")
    elif ecart == -1:
        libelle = t("Yesterday")
    else:
        # The order is the language's: « Nov 3 », « 3 nov. ».
        libelle = t("{month} {day}", month=mois()[jour.month - 1], day=jour.day)
    if carte["colonne"] == "fini" or ecart > 2:
        return libelle, "muted"
    return libelle, "error" if ecart < 0 else "warning"


feature = Feature(
    name="donnees", kind="data",
    provides=[Tableau, colonnes, libelles, MEMBRES, ETIQUETTES, STATUTS,
              semer, copie,
              carte_par_id, colonne_de, occupation, pleine, correspond,
              avancement, entre, depuis, echeance,
              CLES, COULEURS, COUL_ETIQUETTE, INITIALES, LIB_ETIQUETTE, LIMITES, NOMS,
              rang_en_tete],
)
