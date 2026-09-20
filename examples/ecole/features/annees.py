"""features/annees — the year being looked at, and the RT-1 barrier.

``kind="logic"``: the app's shortest feature, and the one every other
will read. It answers two questions, and the whole application depends on
the second.

1. **Which year are we looking at?** A convenience choice, filed in the
   session — it survives a navigation, it follows nobody from one machine
   to another, and it is **not** in the address. EF-U1 lists what the
   address must carry — the class, the term, the tab, the week, the room,
   the sort — and the year is not among them: it is not *what one is
   looking at*, it is *from when one is looking*.

2. **Are we allowed to write?** It is RT-1, and it is a RULE, not a
   screen: *"an entry made by mistake in the previous year would
   otherwise go unnoticed"*. So the guard is a function every write
   calls, and the button one does not show (EF-C10) is only the
   politeness on top.

⚠️ **Why the guard is not in ``db.execute``.** It could not be: the year
concerned depends on the table, and sometimes on a join — a seat on a
plan belongs to a room, which belongs to a class, which belongs to a
year. A guard set at the SQL door would have to rediscover that chain for
every write, or stay silent. Here it takes the year as a parameter: it is
more verbose, and that is the point — one can RE-READ a write function
and see whether it is guarded.
"""

from __future__ import annotations

from functools import partial

from bretzel import Feature, ui
from bretzel.state import SessionState, field
from examples.ecole.core.db import query


class AnneeEnConsultationError(RuntimeError):
    """A write aimed at a year that is not the current one (RT-1).

    A real raise rather than a ``False`` return: a refusal one can ignore
    by forgetting to read the return value is not a barrier. The app
    catches it where it knows what to say on screen; elsewhere it comes
    up, and an error page is better than a silent write into the previous
    year.
    """


class AnneeVue(SessionState):
    """The year THIS browser is looking at. Empty = the current one.

    ⚠️ **Empty is a value, not a hole.** A default identifier would be
    wrong the day the database changes year — and a session state cannot
    read the database to give itself a default. ``""`` means "whichever
    one is current", which stays true after the switch from one school
    year to the next.
    """

    annee: str = field(default="")


def toutes_les_annees() -> list[dict]:
    """The years, most recent first."""
    return query(
        "SELECT id, libelle, debut, fin, en_cours, lundi_ref "
        "FROM annees ORDER BY debut DESC"
    )


def annees_regardee_et_en_cours() -> tuple[dict, dict]:
    """The TWO years that decide everything, in **one single read**.

    They come out of the same list, and asking for them separately read
    it twice. Measured on 2026-09-13 on ``/plan/1``: emptying one seat
    went out on **9 reads of the years table** for 26 SQL queries in
    total, because four zones each called an :func:`en_consultation` that
    cost two.

    If there were no current year — a half-seeded database — the most
    recent stands in: an empty screen would be one more failure to
    diagnose, whereas a year that refuses writing shows on screen. And a
    choice that no longer names anything (a deleted year, a session
    hanging around) falls back on the current year rather than raising: a
    stale setting must not block a page.
    """
    annees = toutes_les_annees()
    en_cours = next((a for a in annees if a["en_cours"]), annees[0])
    choisie = str(AnneeVue().annee)
    if choisie:
        for annee in annees:
            if str(annee["id"]) == choisie:
                return annee, en_cours
    return en_cours, en_cours


def annee_en_cours() -> dict:
    """The year one is allowed to write in (RT-1).

    Only one year is current at a time (§ 5.1).
    """
    return annees_regardee_et_en_cours()[1]


def annee_regardee() -> dict:
    """The year the screen must show — chosen, or the current one."""
    return annees_regardee_et_en_cours()[0]


def en_consultation() -> bool:
    """Are we looking at a year we are not allowed to write?"""
    regardee, en_cours = annees_regardee_et_en_cours()
    return regardee["id"] != en_cours["id"]


def garde_ecriture(annee_id: int) -> None:
    """**The RT-1 barrier.** Raises if ``annee_id`` is not the current
    year.

    To be called on the FIRST line of every function writing dated data.
    It takes the identifier of the year AIMED AT, never that of the year
    being looked at: a write can aim at something other than what the
    screen shows, and that is precisely the case to catch.
    """
    en_cours = annee_en_cours()
    if annee_id != en_cours["id"]:
        raise AnneeEnConsultationError(
            f"Écriture refusée : l'année visée (#{annee_id}) n'est pas "
            f"l'année en cours ({en_cours['libelle']}). Les autres années "
            f"se consultent entièrement et n'acceptent aucune écriture "
            f"(RT-1)."
        )


def options_annees() -> list[tuple[str, str]]:
    """The selector's choices. ``""`` = the current year, named.

    The first entry carries the current year's LABEL and not the words
    "current" alone: the selector must say which year is being looked at,
    not which setting is active.
    """
    annees = toutes_les_annees()
    en_cours = next((a for a in annees if a["en_cours"]), annees[0])
    return [
        ("", f"{en_cours['libelle']} · en cours"),
        *(
            (str(a["id"]), a["libelle"])
            for a in annees
            if a["id"] != en_cours["id"]
        ),
    ]


def changer_annee(vue: AnneeVue) -> None:
    """The teacher changes year; the ``deps=`` zones re-render.

    ⚠️ The body is empty **and that is the mechanism**: the base layer
    has already hydrated ``vue.annee`` before calling the handler, and
    the mutation alone triggers the re-render of the zones declaring
    ``deps=[AnneeVue]``. The TYPED parameter is what hydrates — a handler
    without it would answer zero bytes.
    """


def aller_a_lannee(valeur: str) -> None:
    """Look at another year. ``""`` = the current one.

    The body mutates the state and nothing else: the zones declaring
    ``deps=[AnneeVue]`` re-render on their own.
    """
    AnneeVue().annee = valeur


def selecteur_annee() -> None:
    """The years, as entries in the sidebar's FOOTER (EF-U2).

    They live in the shell and not in a page: the choice bears on ALL the
    screens, so it belongs to the frame.

    ⚠️ **In the footer, and not in a section.** The previous version put
    a ``ui.select`` in the bar's body. Collapsed to a rail, the field was
    squeezed to the rail's width: a two-centimetre box with a chevron and
    nothing else. It is a defect the user reported twice, and that no app
    can fix at home — the collapse is a CLIENT state, so a screen
    rendered by the server does not know it is in one.

    ``ui.sidebar_footer``, for its part, does know: in rail mode it shows
    only the avatar, and its menu floats ABOVE the bar (it goes
    ``position: fixed`` to escape its ``overflow``). It is the answer the
    framework already gives, and it was not being used.
    """
    courante = AnneeVue().annee
    for valeur, libelle in options_annees():
        ui.sidebar_footer_item(
            label=libelle,
            icon_left="check" if valeur == courante else "calendar",
            on_click=partial(aller_a_lannee, valeur),
        )


def bandeau_consultation() -> None:
    """"Année en consultation" — on EVERY screen that would refuse a
    write (EF-U2).

    Rendered in the shell, so there is no screen where it can be
    forgotten. The text says what is forbidden, not only what is true:
    "read only" reads as a state, "no entry is possible" as a
    consequence.
    """
    if not en_consultation():
        return
    ui.banner(
        message=f"{annee_regardee()['libelle']} — année en consultation. "
                f"Aucune saisie n'est possible ; seule "
                f"{annee_en_cours()['libelle']} s'écrit.",
        icon="eye",
        color="warning",
            size="lg",
    )


feature = Feature(
    name="annees",
    kind="logic",
    provides=[
        AnneeVue, AnneeEnConsultationError, toutes_les_annees,
        annees_regardee_et_en_cours, annee_en_cours,
        annee_regardee, en_consultation, garde_ecriture, options_annees,
        changer_annee, selecteur_annee, bandeau_consultation,
    ],
    uses=["db"],
)
