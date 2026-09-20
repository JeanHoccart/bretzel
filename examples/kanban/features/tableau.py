"""kanban/tableau — the columns, the cards, and the activity feed.

Two zones, and **how the two ``@refreshable`` lists are shared is this
example's whole subject**:

- ``deps=`` answers "what makes ME re-render" — the answer arrives in the
  response to my action, one round trip.
- ``broadcast=`` answers "what must the OTHER windows redo" — an SSE
  signal then their own request.

The board is in both: I change it, and the others must see it. The
filters are only in ``deps``: what I hide concerns only me, and
broadcasting it would make everyone work again at every keystroke of a
single person.

**The column that scrolls IS the drop zone**, not a container around it.
Putting the ``dropzone`` inside the scrolling block would make its box
slide with the cards: its frame would cut the middle of the column, and
the "here, you can let go" highlight would leave the screen at the
precise moment it is useful (measured on ``examples/crm``).
"""

from __future__ import annotations

from functools import partial

from bretzel import Feature, page, refreshable, ui
from examples.kanban.core.i18n import tr
from examples.kanban.features.donnees import (
    COUL_ETIQUETTE,
    COULEURS,
    INITIALES,
    LIB_ETIQUETTE,
    NOMS,
    Tableau,
    avancement,
    colonne_de,
    colonnes,
    depuis,
    echeance_lisible,
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
from examples.kanban.features.shell import shell
from examples.kanban.features.state import Affichage, Filtres


def vignette(carte: dict) -> None:
    """A card, as it reads without opening it.

    The click opens the drawer and the drag moves it, without treading on
    each other: the base layer only arms a drag after a pointer movement
    (or a long press with a finger), so a clean click stays a click.
    """
    faites, total = avancement(carte)
    with ui.card(padding="sm", hoverable=True,
                 on_click=partial(ouvrir, carte["id"])), ui.vstack(gap="xs"):
        if carte["etiquettes"]:
            with ui.hstack(gap="xs", wrap=True):
                for cle in carte["etiquettes"]:
                    ui.badge(LIB_ETIQUETTE[cle], size="xs",
                             variant="soft", color=COUL_ETIQUETTE[cle])
        ui.text(carte["titre"], size="sm", weight="medium")
        with ui.hstack(justify="between", align="center", gap="sm"):
            with ui.hstack(gap="sm", align="center"):
                if total:
                    with ui.hstack(gap="xs", align="center"):
                        ui.icon("square-check-big", size="xs",
                                color="success" if faites == total
                                else "muted")
                        ui.text(f"{faites}/{total}", size="xs",
                                color="muted")
                if carte["echeance"]:
                    with ui.hstack(gap="xs", align="center"):
                        ui.icon("calendar", size="xs", color="muted")
                        ui.text(echeance_lisible(carte["echeance"]),
                                size="xs", color="muted")
                if carte["commentaires"]:
                    with ui.hstack(gap="xs", align="center"):
                        ui.icon("message-circle", size="xs",
                                color="muted")
                        ui.text(str(len(carte["commentaires"])),
                                size="xs", color="muted")
            with ui.hstack(gap="xs", align="center"):
                if carte["points"]:
                    ui.badge(str(carte["points"]), size="xs",
                             variant="soft", color="muted")
                ui.avatar(initials=INITIALES[carte["qui"]], size="xs",
                          color=COULEURS[carte["qui"]],
                          tooltip=NOMS[carte["qui"]])


def colonne(cle: str, libelle: str, limite: int | None) -> None:
    """A column: its header, its limit, and its drop zone."""
    filtres = Filtres()
    cartes = colonne_de(cle, filtres.qui, filtres.etiquette, filtres.q)
    dedans = occupation(cle)
    saturee = limite is not None and dedans >= limite

    with ui.vstack(gap="sm", classes="flex-1 min-w-56 min-h-0"):
        with ui.hstack(justify="between", align="center",
                       classes="px-1 shrink-0"):
            with ui.hstack(gap="xs", align="center"):
                ui.heading(libelle, level=2, size="sm")
                # ⚠️ The ``tooltip=`` is set on ALL the columns,
                # including those without a limit. It wraps the badge, so
                # capping only two shifted their headers by two pixels
                # relative to the others — visible on a screenshot.
                ui.badge(
                    f"{dedans} / {limite}" if limite else str(dedans),
                    size="xs", variant="soft",
                    color="error" if saturee else "muted",
                    tooltip=(
                        tr(f"Work-in-progress limit: {limite} cards",
                           f"Limite d'en-cours : {limite} cartes")
                        if limite else
                        tr("No work-in-progress limit",
                           "Pas de limite d'en-cours")
                    ),
                )
            if len(cartes) != dedans:
                montrees = len(cartes)
                ui.text(tr(f"{montrees} shown",
                           f"{montrees} affichée"
                           + ("s" if montrees > 1 else "")),
                        size="xs", color="muted")

        # ⚠️ It is the ZONE that scrolls. ``min-h-0`` is what lets a
        # flex child be SMALLER than its content — without it,
        # ``overflow-y-auto`` has nothing to cut and the column pushes
        # the page.
        with ui.dropzone(
            name=cle, accepts=[GROUPE], on_move=deposer, color="primary",
            classes="flex-1 min-h-0 overflow-y-auto rounded-lg p-2 "
                    + ("bg-error/5" if saturee else "bg-text/5"),
        ), ui.vstack(gap="sm"):
            for carte in ui.drag_each(cartes, group=GROUPE, key="id"):
                vignette(carte)
            if not cartes:
                ui.text(tr("Nothing here. Drop a card.",
                           "Rien ici. Lâche une carte."),
                        size="xs", color="muted",
                        classes="px-1 py-6 text-center")


def bande_archive() -> None:
    """The board's exit: a strip, under the columns.

    ⚠️ **Its height is FIXED and its overflow cut**, and that is not
    fussiness. The drag engine reparents the moved node into the hovered
    zone — it is what makes the DOM order BE the result on drop. A zone
    that lets itself be sized by what it hosts therefore grows by the
    size of a card on hover, and pushes everything around it at the
    precise moment one is aiming. Measured: the first version, set in the
    banner, went from 104×32 to 362×105 and made the whole bar jump from
    93 to 166 px.

    Here the card received is simply cut off: what the reader watches
    during the gesture is the preview under their pointer.
    """
    with ui.dropzone(
        name=ZONE_ARCHIVE, accepts=[GROUPE], locked=True, on_move=archiver,
        color="error",
        classes="flex-none h-14 min-h-0! overflow-hidden rounded-lg "
                "border border-dashed border-text/20 flex items-center "
                "justify-center gap-2",
    ):
        ui.icon("archive", size="sm", color="muted")
        ui.text(tr("Drop a card here to archive it",
                   "Lâche une carte ici pour l'archiver"),
                size="xs", color="muted")


@refreshable(deps=[Tableau, Filtres])
def plateau() -> None:
    """The four columns. Broadcast: what I drag, the others see."""
    with ui.vstack(gap="sm", classes="flex-1 min-h-0 min-w-0 p-4"):
        with ui.hstack(gap="md", align="stretch",
                       classes="flex-1 min-h-0 min-w-0 overflow-x-auto"):
            for cle, libelle, limite in colonnes():
                colonne(cle, libelle, limite)
        bande_archive()


@refreshable(deps=[Tableau])
def activite() -> None:
    """The activity feed — the board's history, newest at the top.

    It is this panel that makes the sharing VISIBLE: in the second
    window, a line appears without anybody having touched it. Entries
    already undone stay shown, set back — the stack is in front of the
    cursor, it is not erased until something is rewritten.

    ⚠️ **Unfolding the panel no longer goes through the server.** It
    lived in ``Vue`` (a server state), so folding a column cost a round
    trip, this zone's re-render, and the wait — to flip a class. Both
    versions are now rendered and ``visible=`` hides one: zero requests,
    and ``Vue`` leaves the zone's dependencies.
    """
    affichage = Affichage()
    tableau = Tableau()

    # The rail, when the panel is folded. Rendered permanently — it is
    # what allows switching without asking anybody anything.
    with ui.vstack(align="center", visible=~affichage.activite,
                   classes="flex-none w-12 border-l border-text/10 pt-4"):
        ui.icon_button("panel-right-open", variant="ghost", size="sm",
                       on_click=affichage.activite.set(True),
                       tooltip=tr("Show the activity",
                                  "Montrer l'activité"))

    with ui.pane(padding="none", gap="none", visible=affichage.activite,
                 classes="flex-none w-80 border-l border-text/10"):
        with ui.hstack(justify="between", align="center",
                       classes="px-4 py-3 shrink-0"):
            ui.heading(tr("Activity", "Activité"), level=2, size="sm")
            ui.icon_button("panel-right-close", variant="ghost", size="sm",
                           on_click=affichage.activite.set(False),
                           tooltip=tr("Hide the activity",
                                      "Cacher l'activité"))
        with ui.pane(padding="md", gap="sm", classes="flex-1 min-h-0"):
            if not tableau.journal:
                ui.text(tr("Nobody has done anything yet. Drag a card.",
                           "Personne n'a encore rien fait. Glisse une "
                           "carte."),
                        size="xs", color="muted")
            for rang, entree in reversed(list(enumerate(tableau.journal))):
                defaite = rang >= tableau.curseur
                with ui.hstack(gap="sm", align="start",
                               classes="opacity-40" if defaite else ""):
                    ui.avatar(initials=INITIALES[entree["qui"]], size="xs",
                              color=COULEURS[entree["qui"]])
                    with ui.vstack(gap="none", classes="min-w-0 flex-1"):
                        ui.text(f"{NOMS[entree['qui']]} {entree['texte']}",
                                size="xs")
                        with ui.hstack(gap="xs", align="center"):
                            ui.text(depuis(entree["t"]), size="xs",
                                    color="muted")
                            if defaite:
                                ui.badge(tr("undone", "annulé"),
                                         size="xs", variant="soft",
                                         color="muted")


@page("/", layout=shell, title="Board")
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
              vignette, bande_archive],
    uses=["donnees", "state", "logic", "shell"],
)
