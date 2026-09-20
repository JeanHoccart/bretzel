"""kanban/shell — the banner, and the frozen frame carrying the board.

``ui.viewport``: the document never scrolls, the columns do, each its
own. It is mandatory for a board — a full column pushing the page down
would take the other three along and the banner with them.

**The filter controls live HERE, outside any ``@refreshable`` zone.** A
zone containing the search field would re-render it at every debounced
keystroke, and the cursor would go back to the start of the word. The
banner is therefore rendered once; only the commands that depend on the
board (undo, redo, the archive) are a zone.

**No ``ui.sidebar``, like the mail client and for the same reason**: the
app has one screen. A kanban's navigation is its columns.
"""

from __future__ import annotations

from functools import partial

from bretzel import (
    Feature,
    Language,
    LiveConnection,
    layout,
    refreshable,
    ui,
)
from bretzel.theme import ColorScheme
from examples.kanban.core.i18n import tr
from examples.kanban.features.donnees import (
    COULEURS,
    ETIQUETTES,
    INITIALES,
    MEMBRES,
    Tableau,
    colonnes,
)
from examples.kanban.features.logic import (
    annuler,
    archiver_ouverte,
    changer_de_membre,
    creer,
    filtrer,
    refaire,
)
from examples.kanban.features.state import Filtres, Moi, Nouvelle, Vue


@refreshable(deps=[Moi])
def identite() -> None:
    """"You are…" — the session identity, changeable in one click.

    Two windows of the same browser share the cookie, hence the same
    identity. To be somebody else you need a private window — or this
    selector, which is enough to see a journal signed by two hands.

    ⚠️ **It is a ZONE, and it took a bug to write it.** The shell is
    rendered ONCE: anything reading a mutable state there without being a
    zone is frozen for the life of the page. The selector, for its part,
    updated on its own — it is a bound control, its value lives in the
    browser — so the screen showed the new name beside the OLD avatar,
    and nothing flagged the contradiction. ``examples/messagerie``'s
    shell carries the same warning, written three days earlier and for
    the same reason.

    ``deps=[Moi]`` alone, with no ``broadcast``: who I am concerns only
    me.
    """
    moi = Moi()
    with ui.hstack(align="center", gap="xs", classes="shrink-0"):
        ui.avatar(initials=INITIALES[moi.membre], size="xs",
                  color=COULEURS[moi.membre])
        ui.select(
            value=moi.membre,
            options=[(cle, nom) for cle, nom, _, _ in MEMBRES],
            on_change=changer_de_membre,
            size="sm",
            classes="w-44",
            tooltip=tr("Who you are on this board",
                       "Qui tu es sur ce tableau"),
        )


def connexion() -> None:
    """The real-time stream's state, bound — so with no zone to refresh.

    Making it a ``@refreshable`` zone would add HTML to every one of the
    responses it claims to describe.
    """
    live = LiveConnection()
    with ui.hstack(align="center", gap="xs", classes="shrink-0"):
        ui.icon("radio", color="success", size="sm", visible=live.connected,
                tooltip=tr("Shared board — the other windows follow",
                           "Tableau partagé — les autres fenêtres "
                           "suivent"))
        ui.icon("radio", color="muted", size="sm", visible=~live.connected,
                tooltip=tr("Stream interrupted", "Flux interrompu"))


def langue() -> None:
    """The language selector — two entries, and the current one is ticked.

    A dropdown and not a toggle: ``Language.set`` is the framework's
    door, it writes a year-long cookie and reloads the page in that
    language. What the app owns is its own sentences
    (:mod:`examples.kanban.core.i18n`); what Bretzel owns is the
    resolution and the transport.

    ⚠️ **What is STORED does not follow the switch**, and it is not a
    gap to fill. The seeded cards and the activity feed are data: they
    were written in the language of the moment, and rewriting them would
    mean throwing away whatever the visitor has typed since. A log
    records what was said, not what one would say today — and a fresh
    session (a private window) seeds its board in the language it opens
    in. Every real app meets the same boundary.
    """
    code = Language().code
    with ui.dropdown(
        trigger=ui.icon_button("languages", variant="ghost", size="sm",
                               tooltip=tr("Language", "Langue")),
        align="end",
    ):
        ui.dropdown_item(
            label="English" + (" ✓" if code.startswith("en") else ""),
            icon_left="languages",
            on_click=partial(Language.set, "en"),
        )
        ui.dropdown_item(
            label="Français" + (" ✓" if code.startswith("fr") else ""),
            icon_left="languages",
            on_click=partial(Language.set, "fr"),
        )


def dialogue_nouvelle() -> None:
    """The creation dialog. Opened by the banner's button."""
    nouvelle = Nouvelle()
    boite = ui.dialog(title=tr("New card", "Nouvelle carte"),
                      width="sm")
    with boite, ui.form(on_submit=[creer, boite.close()]), ui.vstack(gap="md"):
        with ui.form_field(label=tr("Title", "Titre"), required=True):
            ui.input(value=nouvelle.titre, maxlength=120,
                     placeholder=tr("What there is to do",
                                    "Ce qu'il y a à faire"))
        with ui.form_field(label=tr("Column", "Colonne")):
            ui.select(value=nouvelle.colonne,
                      options=[(cle, lib) for cle, lib, _ in colonnes()])
        with ui.hstack(justify="end", gap="sm"):
            ui.button(tr("Cancel", "Annuler"), variant="ghost",
                      on_click=boite.close())
            ui.button(tr("Create", "Créer"), type="submit",
                      color="primary", icon_left="plus")
    ui.button(tr("New card", "Nouvelle carte"), color="primary",
              size="sm", icon_left="plus", on_click=boite.open())


@refreshable(deps=[Tableau, Vue])
def commandes() -> None:
    """Undo, redo, and the archive zone. Broadcast to the others.

    They are a zone because they describe the board: the number of
    possible undos changes when anybody writes, here or elsewhere.
    ``broadcast=[Tableau]`` makes the other windows follow — without it,
    an "Annuler" button would stay greyed out at the neighbour's while
    there is something to undo.
    """
    tableau = Tableau()
    with ui.hstack(align="center", gap="xs", classes="shrink-0"):
        ui.icon_button(
            "undo-2", variant="ghost", size="sm", on_click=annuler,
            disabled=tableau.curseur == 0,
            tooltip=(
                tr("Undo: ", "Annuler : ")
                + tableau.journal[tableau.curseur - 1]["texte"]
                if tableau.curseur
                else tr("Nothing to undo", "Rien à annuler")
            ),
        )
        ui.icon_button(
            "redo-2", variant="ghost", size="sm", on_click=refaire,
            disabled=tableau.curseur >= len(tableau.journal),
            tooltip=(
                tr("Redo: ", "Rétablir : ")
                + tableau.journal[tableau.curseur]["texte"]
                if tableau.curseur < len(tableau.journal)
                else tr("Nothing to redo", "Rien à rétablir")
            ),
        )
        # ⚠️ A BUTTON here, and the drop zone is elsewhere — under the
        # columns. The first version put the ``ui.dropzone`` in this row,
        # and the drag engine REPARENTS the moved node into the hovered
        # zone: the target went from 104×32 to 362×105, and the whole
        # banner from 93 to 166 px tall. The entire bar jumped under the
        # pointer, at the precise moment one is aiming.
        #
        # It is the base layer's optimistic model, not a defect: on drop,
        # the DOM order IS the result. But a zone that will never show
        # what it receives has no business in a row of controls — it is
        # rule A2 of ``livrer-une-app.md``, written the same day and
        # which I had broken.
        ui.button(
            tr("Archive", "Archiver"), variant="outline", size="sm",
            icon_left="archive",
            on_click=archiver_ouverte, disabled=not Vue().ouverte,
            tooltip=tr("Archive the open card — or drop one on the "
                       "strip, at the foot of the board",
                       "Archiver la carte ouverte — ou lâche-en une "
                       "sur la bande, en bas du tableau"),
        )


@layout
def shell() -> None:
    filtres = Filtres()
    with ui.viewport(direction="col"):
        with ui.vstack(gap="none",
                       classes="border-b border-text/10 shrink-0"):
            with ui.hstack(justify="between", align="center", gap="md",
                           classes="px-4 pt-2.5 pb-2"):
                with ui.hstack(align="center", gap="sm"):
                    ui.icon("kanban", color="primary", size="lg")
                    ui.heading(tr("Client portal rework",
                                  "Refonte du portail client"),
                               level=1, size="md")
                    ui.badge("Sprint 24", variant="soft", color="muted",
                             size="xs")
                with ui.hstack(align="center", gap="sm"):
                    connexion()
                    identite()
                    ui.icon_button(
                        "moon", variant="ghost", size="sm",
                        on_click=ColorScheme.toggle(),
                        tooltip=tr("Switch to dark", "Passer en sombre"),
                        classes="dark:!hidden",
                    )
                    ui.icon_button(
                        "sun", variant="ghost", size="sm",
                        on_click=ColorScheme.toggle(),
                        tooltip=tr("Switch to light", "Passer en clair"),
                        classes="!hidden dark:!inline-flex",
                    )
                    langue()

            with ui.hstack(justify="between", align="center", gap="sm",
                           wrap=True, classes="px-4 pb-2.5"):
                with ui.hstack(align="center", gap="sm"):
                    # ``debounce`` on the field: one request per typing
                    # pause, not one per character. The filtering is
                    # SERVER side here — cf. ``state.Filtres``, which
                    # says why the mail client's client-side filter would
                    # be a bug on a board whose cards get dragged.
                    ui.input(
                        value=filtres.q, on_input=filtrer, debounce=350,
                        placeholder=tr("Search a card",
                                       "Rechercher une carte"),
                        icon_left="search", size="sm", clearable=True,
                        classes="w-72",
                    )
                    ui.select(
                        value=filtres.qui, on_change=filtrer, size="sm",
                        classes="w-44",
                        options=[("tous", tr("The whole team",
                                             "Toute l'équipe")),
                                 *[(cle, nom) for cle, nom, _, _ in MEMBRES]],
                    )
                    ui.select(
                        value=filtres.etiquette, on_change=filtrer, size="sm",
                        classes="w-40",
                        options=[("toutes", tr("All labels",
                                               "Toutes étiquettes")),
                                 *[(cle, lib) for cle, lib, _ in ETIQUETTES]],
                    )
                with ui.hstack(align="center", gap="sm"):
                    commandes()
                    dialogue_nouvelle()

        ui.outlet(classes="flex-1 min-h-0 flex")


feature = Feature(
    name="shell", kind="shell",
    provides=[shell, identite, connexion, dialogue_nouvelle, commandes],
    uses=["donnees", "state", "logic"],
)
