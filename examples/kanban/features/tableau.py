"""kanban/tableau — the columns, the cards, and the activity feed.

Two refreshable regions show changes to the current session's board.
They read the board and the filters, so my own action re-renders them
in its response, one round trip. This public demo uses
``SessionState``, so one visitor does not change another's board.

**The column that scrolls IS the drop zone**, not a container around it.
Putting the ``dropzone`` inside the scrolling block would make its box
slide with the cards: its frame would cut the middle of the column, and
the "here, you can let go" highlight would leave the screen at the
precise moment it is useful.
"""

from __future__ import annotations

from functools import partial

from bretzel import Feature, page, refreshable, t, ui
from examples.kanban.features.donnees import (
    COUL_ETIQUETTE,
    COULEURS,
    INITIALES,
    LIB_ETIQUETTE,
    NOMS,
    STATUTS,
    Tableau,
    avancement,
    colonne_de,
    colonnes,
    depuis,
    echeance,
    occupation,
)
from examples.kanban.features.fiche import tiroir
from examples.kanban.features.logic import (
    GROUPE,
    ZONE_ARCHIVE,
    archiver,
    deposer,
    ouvrir,
)
from examples.kanban.features.shell import DESCRIPTION, TITLE, shell
from examples.kanban.features.state import Affichage, Filtres


def indice(icone: str, texte: str, teinte: str = "muted") -> None:
    """One fact of a card's bottom line: a small icon and its value."""
    with ui.hstack(gap="xs", align="center"):
        ui.icon(icone, size="xs", color=teinte)
        ui.text(texte, size="xs", color=teinte)


def vignette(carte: dict) -> None:
    """A card, as it reads without opening it.

    Title, labels, then one line of facts that ends on the owner. The
    owner closes EVERY card, so that line is always drawn and the cards
    of a column share one rhythm; the labels line is skipped when empty.

    Two spacings, not one: the title and its labels are ONE block, held
    close; the facts line stands apart. The padding lives on the inner
    stack (``p-5``) because the card's ``padding=`` steps jump from 12 to
    18 px, and the board wants the step between.

    The click opens the drawer and the drag moves it, without treading on
    each other: the base layer only arms a drag after a pointer movement
    (or a long press with a finger), so a clean click stays a click.
    """
    faites, total = avancement(carte)
    # Not ``hoverable=True``: the shipped relief lifts the card by a
    # pixel and adds a shadow, so the card one is about to click or drag
    # moves under the pointer. Here the hover only lights the border.
    with ui.card(padding="none", on_click=partial(ouvrir, carte["id"]),
                 classes="shadow-xs cursor-pointer transition-colors "
                         "duration-150 hover:border-text/20"), \
            ui.vstack(gap="md", classes="p-5"):
        with ui.vstack(gap="sm"):
            ui.text(carte["titre"], size="sm", weight="medium",
                    classes="leading-snug")
            if carte["etiquettes"]:
                with ui.hstack(gap="xs", wrap=True):
                    for cle in carte["etiquettes"]:
                        ui.badge(LIB_ETIQUETTE[cle], size="sm",
                                 variant="soft", color=COUL_ETIQUETTE[cle])
        # The facts WRAP and the owner does not: in a narrow column the
        # date and the comment count go to a second line rather than push
        # the avatar out of the card.
        with ui.hstack(justify="between", align="center", gap="sm"):
            with ui.hstack(gap="md", align="center", wrap=True,
                           classes="min-w-0"):
                if total:
                    indice("square-check-big", f"{faites}/{total}",
                           "success" if faites == total else "muted")
                libelle, teinte = echeance(carte)
                if libelle:
                    indice("calendar", libelle, teinte)
                if carte["commentaires"]:
                    indice("message-circle", str(len(carte["commentaires"])))
            with ui.hstack(gap="sm", align="center", classes="shrink-0"):
                if carte["points"]:
                    ui.badge(str(carte["points"]), size="sm",
                             variant="soft", color="muted")
                ui.avatar(variant="solid", initials=INITIALES[carte["qui"]], size="xs",
                          color=COULEURS[carte["qui"]],
                          tooltip=NOMS[carte["qui"]])


def colonne(cle: str, libelle: str, limite: int | None) -> None:
    """A column: its status mark, its count, and its drop zone.

    A column at its work-in-progress limit says so on its COUNTER, in
    amber, and nowhere else: a sprint in full swing keeps its limited
    columns full, so the state is normal and must not read as an error.
    """
    filtres = Filtres()
    cartes = colonne_de(cle, filtres.qui, filtres.etiquette, filtres.q)
    dedans = occupation(cle)
    saturee = limite is not None and dedans >= limite
    icone, teinte = STATUTS[cle]

    with ui.vstack(gap="none",
                   classes="flex-1 min-w-[13rem] min-h-0 rounded-box "
                           "bg-text/4"):
        with ui.hstack(justify="between", align="center",
                       classes="px-4 pt-5 pb-3 shrink-0"):
            with ui.hstack(gap="sm", align="center"):
                ui.icon(icone, size="sm", color=teinte)
                ui.heading(libelle, level=2, size="sm", weight="semibold")
                # ⚠️ The ``tooltip=`` is set on ALL the columns,
                # including those without a limit. It wraps the badge, so
                # capping only two shifted their headers by two pixels
                # relative to the others — visible on a screenshot.
                ui.badge(
                    f"{dedans} / {limite}" if limite else str(dedans),
                    size="sm", variant="soft",
                    color="warning" if saturee else "muted",
                    tooltip=(
                        t("Work-in-progress limit: {limite} cards", limite=limite)
                        if limite else
                        t("No work-in-progress limit")
                    ),
                )
            if len(cartes) != dedans:
                montrees = len(cartes)
                ui.text(t("{n} shown", n=montrees, plural="{n} shown"),
                        size="xs", color="muted")

        # ⚠️ It is the ZONE that scrolls. ``min-h-0`` is what lets a
        # flex child be SMALLER than its content — without it,
        # ``overflow-y-auto`` has nothing to cut and the column pushes
        # the page.
        with ui.dropzone(
            name=cle, accepts=[GROUPE], on_move=deposer, color="primary",
            classes="flex-1 min-h-0 overflow-y-auto px-4 pb-4",
        ), ui.vstack(gap="md"):
            for carte in ui.drag_each(cartes, group=GROUPE, key="id"):
                vignette(carte)
            if not cartes:
                ui.text(t("Nothing here. Drop a card."),
                        size="xs", color="muted",
                        classes="px-1 py-6 text-center")


def bande_archive() -> None:
    """The board's exit: a strip under the columns, shown while dragging.

    This is a terminal action, not a fifth column: the runtime reports a
    drop to this zone without inserting a card into its fixed-height box.
    The floating preview stays visible until release.

    At rest it is transparent and lets clicks through; the drag engine
    marks every zone that would accept the card in flight with
    ``data-bz-drop-ok``, and that mark is what makes it appear. It keeps
    its place in the flow all the while: a strip that pushed the columns
    up as the drag starts would move the cards under the pointer.
    """
    with ui.dropzone(
        name=ZONE_ARCHIVE, accepts=[GROUPE], locked=True,
        terminal=True, on_move=archiver,
        color="error",
        classes="flex-none h-12 min-h-0! overflow-hidden rounded-box "
                "border border-dashed border-text/20 flex items-center "
                "justify-center gap-2 opacity-0 pointer-events-none "
                "transition-opacity duration-150 "
                "data-[bz-drop-ok=true]:opacity-100 "
                "data-[bz-drop-ok=true]:pointer-events-auto",
    ):
        ui.icon("archive", size="sm", color="error")
        ui.text(t("Drop here to archive"),
                size="sm", color="error")


@refreshable
def plateau() -> None:
    """The four columns of the current session's board.

    A second window of the same visitor follows the first. ``Tableau``
    is a ``SessionState``, so the signal stays in this session — other
    visitors are neither reached nor re-rendered.
    """
    with ui.vstack(gap="sm",
                   classes="flex-1 min-h-0 min-w-0 px-5 pt-5 pb-3"):
        with ui.hstack(gap="lg", align="stretch",
                       classes="flex-1 min-h-0 min-w-0 overflow-x-auto"):
            for cle, libelle, limite in colonnes():
                colonne(cle, libelle, limite)
        bande_archive()


@refreshable
def activite() -> None:
    """The current board's history, newest at the top.

    Entries already undone stay shown, set back — the stack is in front
    of the cursor, it is not erased until something is rewritten.

    ⚠️ **Folding the panel never goes through the server.** ``Affichage``
    is a client state: the panel's WIDTH follows it through a bound
    ``style=``, and CSS animates the change. One panel, not a panel and a
    rail swapped by ``visible=`` — the toggle sits at the panel's right
    edge in both states, so it stays put while the panel slides around
    it; two swapped elements put it at two different heights.

    The feed has a fixed width and is clipped by the panel, so it slides
    in whole rather than re-wrapping its lines at every frame.
    """
    affichage = Affichage()
    tableau = Tableau()

    with ui.vstack(gap="none",
                   style=affichage.activite.then_else(
                       "width: 18rem", "width: calc(3rem + 1px)"),
                   classes="flex-none min-h-0 overflow-hidden border-l "
                           "border-text/10 transition-[width] duration-200 "
                           "ease-out"):
        # ``px-4``: 12 px either side of a 24 px button is the folded
        # panel's 48 px — plus 1 px for its left border, or the button
        # overflows by that pixel and shifts when the panel folds. So
        # the button is centred on the rail AND at its place when open.
        # The top padding puts the title on the line of the column titles
        # (measured: 29 px, between two 3 px steps).
        with ui.hstack(align="center", gap="none",
                       classes="w-full px-4 pt-[1.8125rem] pb-3 shrink-0"):
            with ui.hstack(gap="sm", align="center",
                           classes="flex-1 min-w-0 overflow-hidden "
                                   "whitespace-nowrap"):
                ui.icon("history", size="sm", color="muted")
                ui.heading(t("Activity"), level=2, size="sm",
                           weight="semibold")
            with ui.hstack(visible=affichage.activite, classes="shrink-0"):
                ui.icon_button("panel-right-close", variant="ghost",
                               size="sm",
                               on_click=affichage.activite.set(False),
                               tooltip=t("Hide the activity"))
            with ui.hstack(visible=~affichage.activite, classes="shrink-0"):
                ui.icon_button("panel-right-open", variant="ghost",
                               size="sm",
                               on_click=affichage.activite.set(True),
                               tooltip=t("Show the activity"))
        with ui.pane(padding="md", gap="md", visible=affichage.activite,
                     classes="flex-1 min-h-0 w-[18rem]"):
            if not tableau.journal:
                ui.empty_state(
                    icon="mouse-pointer-click", size="sm",
                    title=t("Nothing yet"),
                    description=t("Drag a card to another column. Every move is "
                        "logged here, and can be undone."),
                )
            for rang, entree in reversed(list(enumerate(tableau.journal))):
                defaite = rang >= tableau.curseur
                with ui.hstack(gap="sm", align="start",
                               classes="opacity-40" if defaite else ""):
                    ui.avatar(variant="solid", initials=INITIALES[entree["qui"]],
                              size="sm", color=COULEURS[entree["qui"]])
                    with ui.vstack(gap="none", classes="min-w-0 flex-1"):
                        with ui.hstack(gap="xs", align="center"):
                            ui.text(NOMS[entree["qui"]], size="xs",
                                    weight="semibold")
                            ui.text(depuis(entree["t"]), size="xs",
                                    color="muted")
                            if defaite:
                                ui.badge(t("undone"),
                                         size="xs", variant="soft",
                                         color="muted")
                        ui.text(entree["texte"], size="sm",
                                classes="leading-snug")


@page("/", layout=shell, title=TITLE, description=DESCRIPTION)
def page_tableau() -> None:
    # ⚠️ ``align="stretch"`` is not decorative: ``ui.hstack`` aligns on
    # ``center`` by default — the right choice for a row of controls, and
    # fatal for a row of COLUMNS. Without it, each child takes the height
    # of its content instead of the row's: the board's zone measured
    # 878 px inside a 591 px ``<main>``, overflowed at the bottom, and as
    # the document is frozen (``ui.viewport``) nothing scrolled — neither
    # the page, nor the column, whose ``overflow-y-auto`` had nothing
    # left to cut. Invisible on a big screen: at 1500×940 everything
    # fitted, at 1280×700 the cards vanished under the edge. Measured on
    # 2026-09-09 on a screenshot from the user.
    with ui.hstack(gap="none", align="stretch",
                   classes="flex-1 min-h-0 w-full"):
        plateau()
        activite()
    tiroir()


#: ⚠️ ``tiroir`` is declared here although it lives in ``fiche.py``, and
#: it is intended: a ``Feature`` is a SLICE's contract, not a file's. The
#: detail drawer is a region of this page, it has neither a route nor a
#: ``layout=`` — the vocabulary of the ten ``kind`` has nothing, as it
#: happens, for a rendered fragment that is neither. The base layer
#: captures each symbol's DEFINING module, so the map still points at
#: the right file.
feature = Feature(
    name="tableau", kind="page",
    provides=[page_tableau, plateau, activite, tiroir, colonne,
              vignette, indice, bande_archive],
    uses=["donnees", "state", "logic", "shell"],
)
