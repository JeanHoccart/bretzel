"""features/emploi_du_temps — page: the week's grid. The opening.

*"It is the opening screen"* (§ 8 of the specification), and it is the
twenty-seconds-on-the-doorstep screen. EF-B1 to EF-B14.

The three modes, and why there are three and not two
-----------------------------------------------------
========================  ==================================================
mode                      what is done there
========================  ==================================================
**reading** (the default) one looks at the week. The days without class
                          are EMPTY and carry their period's name
**modification**          one reworks the TYPICAL grid. *"It is during
                          the holidays that there is time to rework the
                          grid"* — so **everything comes back** (EF-B5)
**exceptions**            one sets an extra hour or a cancellation on a
                          REAL date (EF-B11)
========================  ==================================================

There are three because the last two do not write the same thing: the
modification touches the grid that repeats, the exception touches one
precise day. Confusing them is cancelling every Monday while believing
one is cancelling this one.

What the screen REFUSES to show, and it is trap no. 12
-------------------------------------------------------
*"Greying out the holiday days while leaving the classes readable is not
enough — one still reads five lessons that will not happen."* So a day
without class is EMPTY, and the period's name is written under the date
(EF-B4). In modification mode it fills up again: the typical grid is
never erased, it is the days that do not apply it.

And what it refuses to build
-----------------------------
**No "Maintenant: 4e3" banner** (EF-B16). It was built then removed in
BOTH real applications, for the same reason: the grid is just below and
says the same thing better, and the banner occupied the screen's first
line even with nothing to say.

⚠️ The layout is not a CSS grid with ``row-span``
--------------------------------------------------
It was for an hour, and it is wrong: a CSS grid's automatic placement is
SEQUENTIAL, so a cell overflowing three rows shifts every following one
by a column — Wednesday ends up under Tuesday. Here, **seven columns each
stacking their own cells**, all at the same height, and a three-hour
block takes the height of three cells through a computed ``style=``. The
columns stay aligned because every cell weighs exactly the same.

⚠️ And no Tailwind class is ASSEMBLED in an f-string: a built class
(``bg-{colour}/5``) only exists in development, where the compiler runs
in the browser — in production it disappears without an error. So the
three tints are WHOLE strings, in a closed table.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, timedelta
from functools import partial

from bretzel import Feature, page, refreshable, ui
from bretzel.state import PageState, field
from bretzel.theme import DEFAULT_SPACING_PX
from examples.ecole.core.domain import JOURS, est_un_tp, jour_et_date
from examples.ecole.features.annees import (
    AnneeVue,
    annee_regardee,
    en_consultation,
)
from examples.ecole.features.grille_data import (
    annuler_derniere_grille,
    classe_id_de,
    lundi_affiche,
    poser_case,
    poser_exception,
    regler_horaire,
    retirer_exception,
    semaine_affichee,
)
from examples.ecole.features.shell import shell
from examples.ecole.features.suivi import cadres_du_jour

PATH = "/"

#: Seven columns: the time slots, then the six days.
#:
#: ⚠️ **In ``px``, not in ``rem``.** A width written in ``rem`` follows
#: the text size, and the week stops fitting on screen as soon as that
#: moves. Measured with the 19 px base the app carried for a while: the
#: grid asked for 1 178 px on its own, and Friday and Saturday went
#: behind a scrollbar — on the screen whose WHOLE point is to be read at
#: a glance. A column's width belongs to the screen, not to the text.
COLONNES = "grid-cols-[56px_repeat(6,minmax(88px,1fr))]"

#: The height of ONE hour and the space between two, **in pixels**. Both
#: serve to compute the height of an N-hour block — hence numbers and not
#: classes: ``h-24`` cannot add up.
#:
#: 64 px, and the calculation is worth writing down because it got it
#: wrong three times. A cell shows TWO lines — the class code, then the
#: room and the link to the log — that is 42 px of text at the preset's
#: scale (14 px, normal leading). The rest is the FRAME:
#: ``ui.card(padding="xs")`` sets 8 px on each side, plus a hairline. A
#: card has ``overflow:hidden``, so anything not fitting in that count
#: disappears **without a word** — no error, no trace, and complete HTML.
#:
#: ⚠️ 72 and not 64: the count "two lines plus the frame" was right and
#: INCOMPLETE — an underlined link descends below its baseline, and the
#: card has a hairline. The probe gave the exact figure (68), the head
#: gave 60. It is the day's fourth value, and the only one not guessed.
#:
#: The history says why the probe's finding (24) exists: at 52 px an
#: hour lost its room; at 64 px with ``padding="sm"`` the frame ate 32 px
#: of the 62 usable and 80 were needed; at 80 px with the preset, two
#: thirds of the cell were empty. It is finding F9, and none of those
#: three values was guessable by reading the code.
HAUTEUR_CASE = 72

#: The space between two cells, **DERIVED and no longer copied**.
#:
#: The columns are ``ui.vstack(gap="xs")``, that is ``gap-1``, that is
#: one spacing step. Reading it from the preset instead of writing it
#: here removes finding F10's whole class: the value can no longer
#: diverge from the one the column really sets.
#:
#: ⚠️ It had diverged twice. 6 px for a ``gap-1`` of 4, then 4 for a
#: ``gap-1`` become 3 when the density moved to a 3 px step. The defect
#: shows on no one-hour cell — it only serves the BLOCKS, which slip by
#: that much per extra hour.
ESPACE_CASE = DEFAULT_SPACING_PX

#: A row's pitch: the cell plus its space. It is the background rule's
#: period, and the only way the lines fall EXACTLY between two cells.
PAS_RANGEE = HAUTEUR_CASE + ESPACE_CASE

#: The horizontal rule of real calendars, drawn as a BACKGROUND.
#:
#: ⚠️ **As a background and not a border**, and it is what changes
#: everything. A border lives on a cell, so it stops where there is a
#: cell: the grid was a chequerboard of cards floating in a void, with no
#: landmark to align a lesson with its hour. The background, for its
#: part, depends on no content — it continues under the blocks and
#: through the empty hours, exactly like a diary's ruling.
#:
#: ⚠️ A neutral grey at low opacity rather than a theme token: the same
#: value must hold on the light paper and on the dark grey, and a rule
#: that follows the text colour vanishes on one side or shouts on the
#: other.
FILET = "rgba(128,128,128,0.16)"


def fond_de_colonne(rangs: int) -> str:
    """A column's ``style=``: its height and its ruling.

    The ruling repeats on :data:`PAS_RANGEE` and puts its line on the
    last pixel — so in the inter-cell space, never under a card.
    """
    haut = rangs * HAUTEUR_CASE + (rangs - 1) * ESPACE_CASE
    return (
        f"height:{haut}px;"
        f"background-image:repeating-linear-gradient(to bottom,"
        f"transparent 0,transparent {HAUTEUR_CASE}px,"
        f"{FILET} {HAUTEUR_CASE}px,{FILET} {HAUTEUR_CASE + 1}px,"
        f"transparent {HAUTEUR_CASE + 1}px,transparent {PAS_RANGEE}px)"
    )

#: A column header's height, **fixed for all seven**.
#:
#: ⚠️ Without a fixed height, each column sizes itself on ITS content: a
#: holiday day carries one more line (the period's name, EF-B4), so ITS
#: column drops a step and its cells stop facing the time slots. The
#: shift only appears in holiday weeks, which is the worst way of finding
#: it.
#:
#: 44 px: two short lines at the preset's scale, plus the rule.
HAUTEUR_ENTETE = 44

#: A cell's three tints, as WHOLE strings. A closed table, because an
#: assembled class only exists in dev (cf. the header).
#: ⚠️ **No full frame, a hairline on the LEFT.** An outline on all four
#: sides reads as a button; it is the case in every calendar worth
#: copying — the event is a tinted surface its left bar identifies.
#: Thirty outlines in a grid make a chequerboard, thirty surfaces make a
#: week.
#: WHOLE strings, never assembled: a class built in an f-string does not
#: exist in the production sheet.
TEINTES: dict[str, str] = {
    "cours": ("bg-primary/12 border-l-[3px] border-l-primary "
              "rounded-r-md overflow-hidden px-2 py-1"),
    "nature": ("bg-warning/12 border-l-[3px] border-l-warning "
               "rounded-r-md overflow-hidden px-2 py-1"),
    "exception": ("bg-info/12 border-l-[3px] border-l-info "
                  "rounded-r-md overflow-hidden px-2 py-1"),
}

#: The three modes, their label and their icon.
MODES: tuple[tuple[str, str, str], ...] = (
    ("lecture", "Lecture", "eye"),
    ("modification", "Modifier la grille", "pencil"),
    ("exceptions", "Heures exceptionnelles", "calendar-clock"),
)


class SemaineVue(PageState, addressable=True):
    """The week shown — **and the address is authoritative** (EF-U1).

    *"A screen one cannot send back by a link is not shareable with
    oneself the next day"*: ``/?semaine=2026-11-16`` opens that week for
    whoever receives the link.

    Empty = today's week. A COMPUTED default would be frozen at process
    startup and wrong the next day; an empty default stays right every
    day.
    """

    lundi: str = field(default="", url="semaine")


class ModeGrille(PageState):
    """The grid's mode, and the cell being edited.

    A ``PageState`` with no address: a mode is not *what one is looking
    at* but *what one is doing*. Putting it in the URL would open the
    screen of whoever receives the link in modification mode.
    """

    mode: str = field(default="lecture")
    ouvert: bool = field(default=False)
    jour: int = field(default=0)
    rang: int = field(default=1)
    date_iso: str = field(default="")
    occupee: bool = field(default=False)
    saisie: str = field(default="")


class HoraireDraft(PageState):
    """A slot's boundaries, set for the whole year (EF-B3)."""

    ouvert: bool = field(default=False)
    rang: int = field(default=1)
    debut: str = field(default="")
    fin: str = field(default="")


def hauteur(rangs: int) -> str:
    """The ``style=`` of a cell covering ``rangs`` hours."""
    total = rangs * HAUTEUR_CASE + (rangs - 1) * ESPACE_CASE
    return f"height:{total}px"


# ── Les handlers ─────────────────────────────────────────────────────

def aller_a(decalage: int) -> None:
    """The week arrows (EF-B1). ``0`` brings back to today."""
    vue = SemaineVue()
    if decalage == 0:
        vue.lundi = ""
        return
    courant = lundi_affiche(annee_regardee(), str(vue.lundi))
    vue.lundi = (courant + timedelta(weeks=decalage)).isoformat()


def changer_mode(mode: str) -> None:
    etat = ModeGrille()
    etat.mode = mode
    etat.ouvert = False


def ouvrir_case(jour: int, rang: int, date_iso: str, occupee: bool,
                saisie: str) -> None:
    etat = ModeGrille()
    etat.jour = jour
    etat.rang = rang
    etat.date_iso = date_iso
    etat.occupee = occupee
    etat.saisie = saisie
    etat.ouvert = True


def fermer_case(etat: ModeGrille) -> None:
    etat.ouvert = False


def lettre_affichee() -> str | None:
    """The letter of the week shown — DEDUCED, never chosen (EF-B2)."""
    annee = annee_regardee()
    lundi = lundi_affiche(annee, str(SemaineVue().lundi))
    return semaine_affichee(annee, lundi)["lettre"]


def enregistrer_case(etat: ModeGrille) -> None:
    """EF-B6's gesture: a code is typed, the cell takes it.

    The letter comes from the week SHOWN and is therefore not a form
    field: it is not chosen. Without a reference date, we do not know
    which half of the grid we are writing — and writing anyway would set
    the lesson every other week, at random.
    """
    lettre = lettre_affichee()
    if not lettre:
        ui.notification(
            "Sans date de référence de semaine A, on ne sait pas quelle "
            "semaine on modifie. À régler dans les Réglages.",
            variant="warning", duration_ms=5000)
        etat.ouvert = False
        return
    code = poser_case(annee_regardee()["id"], int(etat.jour), int(etat.rang),
                      lettre, str(etat.saisie))
    etat.ouvert = False
    ui.notification(
        f"{code} posée en semaine {lettre}" if code else "Case vidée",
        variant="success", duration_ms=2000)


def annuler_lheure(etat: ModeGrille) -> None:
    """An OCCUPIED cell offers only a cancellation (EF-B11).

    *One is not in two places at once*: offering to add a class on an
    hour already taken would make no sense.
    """
    poser_exception(annee_regardee()["id"], str(etat.date_iso),
                    int(etat.rang), "")
    etat.ouvert = False


def ajouter_lheure(etat: ModeGrille) -> None:
    """A FREE cell offers only an addition — there is nothing to cancel."""
    code = str(etat.saisie).strip()
    if code:
        poser_exception(annee_regardee()["id"], str(etat.date_iso),
                        int(etat.rang), code)
    etat.ouvert = False


def rendre_a_la_grille(etat: ModeGrille) -> None:
    retirer_exception(annee_regardee()["id"], str(etat.date_iso),
                      int(etat.rang))
    etat.ouvert = False


def revenir_en_arriere() -> None:
    if annuler_derniere_grille(annee_regardee()["id"]):
        ui.notification("Grille rendue telle qu'elle était",
                        variant="success", duration_ms=2000)
        return
    ui.notification("Aucune modification à annuler", variant="info",
                    duration_ms=2000)


def ouvrir_horaire(rang: int, debut: str, fin: str) -> None:
    draft = HoraireDraft()
    draft.rang = rang
    draft.debut = debut
    draft.fin = fin
    draft.ouvert = True


def enregistrer_horaire(draft: HoraireDraft) -> None:
    regler_horaire(annee_regardee()["id"], int(draft.rang),
                   str(draft.debut), str(draft.fin))
    draft.ouvert = False


# ── Le rendu ─────────────────────────────────────────────────────────

def cellule_bloc(bloc: dict, rangs: int, cible: int | None,
                 jour: str = "", changer: Callable[[], None] | None = None,
                 fige: bool = False, geste: tuple[str, str] = ("", "")) -> None:
    """An occupied cell: the class, its room, its practical, its badge.

    **EF-B14 — the cell leads to TWO places**: the class, and the lesson
    log with the class AND the date. *"It is the shortest path between
    'what did I do on Monday?' and the answer."*

    ⚠️ **These are two LINKS in an ordinary card, and above all not a
    link-card containing a second one.** The first version did that —
    ``ui.card(href=…)`` with a ``ui.link`` inside — and the result was
    broken in a way no test saw: HTML forbids an ``<a>`` inside an
    ``<a>``, so the browser's parser CLOSES the outer link on meeting the
    inner one, and everything that follows leaves the card. Measured: the
    card rendered 130 px of emptiness, and the room's name showed below
    it, in the next hour's cell. The serialised HTML was correct — it is
    the parser that rewrites it.
    """
    # A 2 px hairline and not 4: a grid of thirty cells is a WALL, and
    # it is the amber of a nature or the red of a refusal that must show
    # there — not the ordinary case.
    teinte = TEINTES["nature"] if bloc["nature"] else (
        TEINTES["exception"] if bloc.get("exception") else TEINTES["cours"])
    # ⚠️ No more ``ui.card``: its theme sets an outline on all four
    # sides, and thirty outlines in a grid make a chequerboard. A diary
    # event is a tinted SURFACE its left bar identifies — it is what
    # every calendar one opens without thinking does. The catch-up would
    # have been a ``border-0`` set in ``classes=`` over the theme; this
    # is one component FEWER, not one class more.
    with ui.vstack(gap="none", classes=teinte, style=hauteur(rangs)):
        with ui.hstack(gap="sm", justify="between", align="center"):
            # The class code is written the SAME, link or not: it is
            # ``ui.text`` that carries its weight, in both branches.
            # ``ui.link`` has neither ``weight=`` nor ``size=``, and
            # catching that up in ``classes=`` would have made two
            # vocabularies say the same thing — the component's on one
            # side, Tailwind on the other.
            if cible:
                with ui.link(href=f"/classe/{cible}", variant="hover"):
                    ui.text(bloc["code"], weight="semibold")
            else:
                ui.text(bloc["code"], weight="semibold")
            with ui.hstack(gap="sm", align="center"):
                if changer is not None:
                    # ⚠️ INSIDE the cell, and not below it. The
                    # previous version stacked the card and a "Changer"
                    # button in a frame of height `hauteur(rangs)` — so
                    # content taller than its box: the button came out at
                    # the bottom, covered the next cell, and the card cut
                    # its second line. Seen on screen.
                    #
                    # Putting it here has a second effect, more important
                    # than the first: the grid NO LONGER MOVES when going
                    # from reading to modification. One edits what one
                    # was looking at, in the same place.
                    mot, icone = geste
                    ui.icon_button(
                        icone, variant="ghost", size="sm",
                        aria_label=f"{mot} {bloc['code']}",
                        tooltip=f"{mot} {bloc['code']}",
                        disabled=fige, on_click=changer,
                    )
                if est_un_tp(bloc):
                    # EF-B10: nothing is entered or stored — the rule
                    # is READ from the grid.
                    ui.badge(label="TP", color="primary", variant="soft",
                             size="lg")
                if bloc["consignee"]:
                    # EF-B13: at a glance over the week, what is left
                    # to write in the lesson log.
                    ui.icon("book-check", color="success",
                            tooltip="Consignée au cahier de texte")
        with ui.hstack(gap="sm", align="center", wrap=True):
            if bloc["nature"]:
                ui.text(bloc["nature"], color="warning")
            if bloc["salles"]:
                ui.text(" · ".join(bloc["salles"]), color="muted")
            if cible and jour:
                ui.link(
                    label="cahier",
                    href=f"/cahier?classe={cible}&date={jour}",
                    variant="underline", color="muted",
                    tooltip="Le cahier de texte de ce jour-là",
                )


def case_vide(mode: str, rangs: int = 1) -> None:
    """What occupies the place of an hour with no lesson.

    In reading, emptiness. In modification, a dotted frame: a free cell
    must look like a target, otherwise one does not know where to click.
    """
    classes = ("rounded-lg border border-dashed border-text/15"
               if mode != "lecture" else "")
    ui.flex(classes=classes, style=hauteur(rangs))


def colonne_du_jour(jour: dict, index: int, bornes: dict, mode: str,
                    fige: bool, aujourdhui: date,
                    annee_id: int) -> None:
    """A day: its header, then its cells from top to bottom.

    The column reads in TWO storeys, and it is what makes it readable:
    the header, then a frame carrying the horizontal ruling and all the
    cells. The rule lives on the frame, so it continues under the blocks
    and through the empty hours — a border set on the cells would stop
    where there is no cell, that is to say exactly where the eye needs
    it.
    """
    vide_ce_jour = bool(jour["periode"]) and mode != "modification"
    dernier = max(bornes)
    with ui.vstack(gap="xs", classes="border-l border-text/10"):
        entete_de_jour(jour, aujourdhui)
        with ui.vstack(gap="xs", style=fond_de_colonne(dernier)):
            rang = 1
            while rang <= dernier:
                bloc = next(
                    (b for b in jour["blocs"] if b["debut"] == rang), None)
                if vide_ce_jour:
                    # Trap no. 12: EMPTY, not greyed out. One would
                    # still read the five lessons that will not happen.
                    case_vide("lecture")
                    rang += 1
                    continue
                if bloc is None:
                    if mode == "lecture":
                        case_vide("lecture")
                    else:
                        bouton_de_case(jour, index, rang, mode, fige,
                                       occupee=False, saisie="")
                    rang += 1
                    continue
                rangs = bloc["fin"] - bloc["debut"] + 1
                if mode == "lecture":
                    # The link only opens IN READING mode: in
                    # modification, a click on the cell must set a class,
                    # not navigate elsewhere.
                    cellule_bloc(
                        bloc, rangs, classe_id_de(annee_id, bloc["code"]),
                        jour["date"].isoformat())
                else:
                    cellule_bloc(
                        bloc, rangs, None, fige=fige,
                        geste=(("Annuler", "calendar-x")
                               if mode == "exceptions"
                               else ("Changer", "pencil")),
                        changer=partial(ouvrir_case, index, rang,
                                        jour["date"].isoformat(), True,
                                        bloc["code"]),
                    )
                rang = bloc["fin"] + 1


def entete_de_jour(jour: dict, aujourdhui: date) -> None:
    """The column carries the REAL DATE, and today is marked.

    A FIXED height: cf. :data:`HAUTEUR_ENTETE`. A holiday day carries one
    more line, and without this constraint it would shift its one column
    by a step — Tuesday facing the wrong hour, in the Toussaint week and
    not the others.
    """
    cest_aujourdhui = jour["date"] == aujourdhui
    with ui.vstack(
        gap="none", align="center", justify="center",
        style=f"height:{HAUTEUR_ENTETE}px",
        classes="border-b-2 " + (
            "border-primary" if cest_aujourdhui else "border-text/10"),
    ):
        ui.text(JOURS[jour["date"].weekday()].capitalize(),
                size="sm",
                weight="semibold" if cest_aujourdhui else None,
                color="primary" if cest_aujourdhui else None)
        if jour["periode"]:
            # EF-B4: the period's name UNDER the date. An empty column
            # with no explanation reads as a failure.
            ui.text(jour["periode"], color="warning", truncate=True)
        else:
            # ⚠️ The DATE alone: ``jour_et_date`` returns "lun 07/09",
            # and the line above already says "Lundi". The same word
            # twice in a header three centimetres wide.
            ui.text(jour["date"].strftime("%d/%m"),
                    size="sm", color="muted", classes="tabular-nums")


def bouton_de_case(jour: dict, index: int, rang: int, mode: str, fige: bool,
                   *, occupee: bool, saisie: str) -> None:
    if mode == "exceptions":
        # EF-B11: the occupied cell offers only a cancellation, the
        # free cell only an addition. The label says which of the two,
        # and it is the only thing distinguishing them on screen.
        libelle = "Annuler" if occupee else "Ajouter"
        icone = "calendar-x" if occupee else "calendar-plus"
    else:
        libelle = "Changer" if occupee else "Poser"
        icone = "pencil" if occupee else "plus"
    # ⚠️ ``ghost`` and ``muted`` for a FREE cell: a grid of forty
    # targets ringed in the accent colour shouts louder than the five
    # lessons it surrounds. In a diary, emptiness is a background, not a
    # button — it becomes a target on hover and from the keyboard, and
    # the rest of the time it keeps quiet.
    ui.button(
        libelle, variant="ghost", color="muted", icon_left=icone,
        disabled=fige,
        classes="w-full", style=hauteur(1) if not occupee else "",
        on_click=partial(ouvrir_case, index, rang,
                         jour["date"].isoformat(), occupee, saisie),
    )


def colonne_horaires(bornes: dict[int, tuple[str, str]], fige: bool) -> None:
    """The FIRST column, where the boundaries are set (EF-B3)."""
    with ui.vstack(gap="xs"):
        with ui.vstack(gap="none", align="center", justify="center",
                       style=f"height:{HAUTEUR_ENTETE}px",
                       classes="border-b-2 border-text/10"):
            ui.text("Horaires", color="muted", weight="semibold",
                    size="sm")
        # The gutter carries the SAME ruling as the days: without it,
        # the hours float beside a ruled grid, and it is precisely that
        # alignment one is trying to give the eye.
        with ui.vstack(gap="xs", style=fond_de_colonne(max(bornes))):
            for rang in sorted(bornes):
                debut, fin = bornes[rang]
                # ⚠️ The START time alone, and set at the TOP of its
                # row. It is every diary's convention, and it is not a
                # taste: an hour centred in its band marks no boundary,
                # so the eye does not know where a two-hour block
                # starts. The end reads on the next line; the last
                # slot's lives in the settings dialog, which carries
                # both.
                ui.button(
                    debut, variant="ghost", disabled=fige, size="sm",
                    classes="w-full justify-end items-start pt-1 "
                            "whitespace-nowrap tabular-nums",
                    style=hauteur(1),
                    on_click=partial(ouvrir_horaire, rang, debut, fin),
                )


def barre_de_semaine(lundi: date, lettre: str | None, mode: str,
                     fige: bool) -> None:
    samedi = lundi + timedelta(days=5)
    with ui.hstack(gap="md", justify="between", align="center", wrap=True):
        with ui.hstack(gap="sm", align="center"):
            ui.icon_button("chevron-left", variant="outline",
                           aria_label="Semaine précédente",
                           on_click=partial(aller_a, -1))
            ui.button("Aujourd'hui", variant="ghost",
                      on_click=partial(aller_a, 0))
            ui.icon_button("chevron-right", variant="outline",
                           aria_label="Semaine suivante",
                           on_click=partial(aller_a, 1))
            ui.text(f"{jour_et_date(lundi)} — {jour_et_date(samedi)}",
                    weight="medium")
            # EF-B2: the letter is DEDUCED from the week shown and
            # displayed at the head. It is not chosen — so there is no
            # control here, just the result.
            if lettre:
                ui.badge(label=f"Semaine {lettre}", color="primary",
                         variant="solid", size="xl")
            else:
                ui.badge(label="semaine indéterminée", color="warning",
                         variant="soft", size="xl")
        with ui.hstack(gap="sm", align="center", wrap=True):
            for valeur, libelle, icone in MODES:
                ui.button(
                    libelle,
                    variant="solid" if mode == valeur else "outline",
                    icon_left=icone, disabled=fige and valeur != "lecture",
                    on_click=partial(changer_mode, valeur),
                )
            if mode == "modification":
                ui.button("Annuler la dernière modification",
                          variant="ghost", icon_left="undo-2", disabled=fige,
                          on_click=revenir_en_arriere)


# ``HoraireDraft`` is NOT in this list: the grid does not read it. It
# was there to refresh ``dialogue_horaire``, which was called here — so
# opening a slot's boundaries redrew the whole week.
@refreshable(deps=[AnneeVue, SemaineVue, ModeGrille])
def grille() -> None:
    annee = annee_regardee()
    etat = ModeGrille()
    lundi = lundi_affiche(annee, str(SemaineVue().lundi))
    semaine = semaine_affichee(annee, lundi)
    mode = str(etat.mode)
    fige = en_consultation()

    with ui.vstack(gap="md"):
        barre_de_semaine(lundi, semaine["lettre"], mode, fige)
        if not semaine["lettre"]:
            ui.banner(
                message="Aucune date de référence de semaine A : "
                        "l'alternance est indéterminée, donc la grille type "
                        "n'est pas lisible. À régler dans les Réglages.",
                icon="circle-help", color="warning",
                            size="lg",
            )
        with ui.grid(gap="xs", classes=COLONNES):
            colonne_horaires(semaine["bornes"], fige)
            for index, jour in enumerate(semaine["jours"]):
                colonne_du_jour(jour, index, semaine["bornes"], mode, fige,
                                date.today(), annee["id"])


@refreshable(deps=[ModeGrille])
def dialogue_de_case() -> None:
    etat = ModeGrille()
    if str(etat.mode) == "exceptions":
        dialogue_exception(etat)
        return
    with (
        ui.dialog(open=etat.ouvert, title="Poser une classe",
                  on_close=fermer_case),
        ui.form(on_submit=enregistrer_case),
        ui.vstack(gap="md"),
    ):
        ui.text(
            "Tapez le code de la classe. Un code inconnu la CRÉE, vide — "
            "l'emploi du temps arrive fin août, les listes d'élèves à la "
            "rentrée. Ce qui suit se lit comme une SALLE, sauf les mots de "
            "la liste des natures (HVC), qui retirent l'heure du cahier de "
            "texte. Laisser vide efface la case.",
            color="muted",
        )
        with ui.form_field(label="Classe, nature, salle",
                           hint="4e1 · 3e4 (L) · 2°GT2 - 134 · 4e2 - HVC"):
            ui.input(value=etat.saisie, placeholder="4e1 - L")
        with ui.hstack(justify="end"):
            ui.button("Poser", type="submit", color="primary")


def dialogue_exception(etat: ModeGrille) -> None:
    occupee = bool(etat.occupee)
    titre = "Annuler cette heure" if occupee else "Ajouter une heure"
    with ui.dialog(open=etat.ouvert, title=titre, on_close=fermer_case):
        if occupee:
            with ui.vstack(gap="md"):
                ui.text(
                    "Cette heure est déjà prise : on n'est pas à deux "
                    "endroits à la fois, donc la seule décision possible "
                    "est de l'annuler pour cette date.",
                    color="muted",
                )
                with ui.hstack(gap="md", justify="between"):
                    ui.button("Rendre à la grille type", variant="ghost",
                              on_click=rendre_a_la_grille)
                    ui.button("Annuler cette heure", color="error",
                              icon_left="calendar-x", on_click=annuler_lheure)
            return
        with ui.form(on_submit=ajouter_lheure), ui.vstack(gap="md"):
            ui.text(
                "Cette case est libre : il n'y a rien à y annuler, "
                "seulement une heure à y ajouter, pour cette date.",
                color="muted",
            )
            with ui.form_field(label="Classe"):
                ui.input(value=etat.saisie, placeholder="4e1")
            with ui.hstack(gap="md", justify="between"):
                ui.button("Rendre à la grille type", variant="ghost",
                          on_click=rendre_a_la_grille)
                ui.button("Ajouter", type="submit", color="primary")


@refreshable(deps=[HoraireDraft])
def dialogue_horaire() -> None:
    draft = HoraireDraft()
    with (
        ui.dialog(open=draft.ouvert, title="Bornes de ce créneau"),
        ui.form(on_submit=enregistrer_horaire),
        ui.vstack(gap="md"),
    ):
        ui.text("Réglé pour toute l'année, sur les six jours.", color="muted")
        with ui.grid(cols={"base": 1, "md": 2}, gap="md"):
            with ui.form_field(label="Début"):
                ui.time_picker(value=draft.debut)
            with ui.form_field(label="Fin"):
                ui.time_picker(value=draft.fin)
        with ui.hstack(justify="end"):
            ui.button("Enregistrer", type="submit", color="primary")


@page(PATH, layout=shell, title="Emploi du temps")
def emploi_du_temps_page() -> None:
    with ui.vstack(gap="lg"):
        ui.heading("Emploi du temps", level=1, size="2xl")
        # EF-B15: the start-of-lesson frames, at the HEAD of the grid.
        # It is not EF-B16's "Maintenant" banner: that one repeated what
        # the grid says better, this one carries what can be read nowhere
        # else — the last session held and the work to check.
        cadres_du_jour()
        grille()
    # Mounted by the PAGE: a zone called inside another goes out with
    # it, and these two dialogs are closed almost all the time.
    dialogue_de_case()
    dialogue_horaire()


feature = Feature(
    name="emploi_du_temps",
    kind="page",
    provides=[emploi_du_temps_page, SemaineVue, ModeGrille, HoraireDraft],
    uses=["grille_data", "annees", "shell", "suivi"],
)
