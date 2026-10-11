"""kanban/shell — the banner, and the frozen frame carrying the board.

``ui.viewport``: the document never scrolls, the columns do, each its
own. It is mandatory for a board — a full column pushing the page down
would take the other three along and the banner with them.

**One row**, read left to right as a sentence: which board, which cards,
what I can do. The project and its sprint, then the filters, then the
history, the display settings, who I am, and the one creative action.

**The filter controls live HERE, outside any ``@refreshable`` zone.** A
zone containing the search field would re-render it at every debounced
keystroke, and the cursor would go back to the start of the word. The
banner is therefore rendered once; only what depends on a mutable state
(the undo history, who I am) is a zone.

**No ``ui.sidebar``, like the mail client and for the same reason**: the
app has one screen. A kanban's navigation is its columns.
"""

from __future__ import annotations

from functools import partial

from bretzel import (
    Feature,
    Language,
    LiveConnection,
    auth,
    copy,
    layout,
    refreshable,
    ui,
)
from bretzel.render import current_context
from bretzel.theme import ColorScheme
from examples.kanban.core.i18n import tr
from examples.kanban.features.donnees import (
    COULEURS,
    ETIQUETTES,
    INITIALES,
    MEMBRES,
    NOMS,
    Tableau,
    colonnes,
)
from examples.kanban.features.logic import (
    annuler,
    creer,
    devenir,
    filtrer,
    refaire,
)
from examples.kanban.features.state import Filtres, Moi, Nouvelle


@refreshable(deps=[Moi])
def identite() -> None:
    """"You are…" — the session identity, changeable in one click.

    Two windows of the same browser share the cookie, hence the same
    identity. To be somebody else you need a private window — or this
    menu, which is enough to see a journal signed by two hands.

    ⚠️ **It is a ZONE.** The shell is rendered ONCE: anything reading a
    mutable state there without being a zone is frozen for the life of
    the page, and the trigger would keep showing the previous person.

    ``deps=[Moi]`` alone, with no ``broadcast``: who I am concerns only
    me.
    """
    moi = Moi().membre
    with ui.dropdown(
        trigger=ui.button(
            NOMS[moi].split()[0], variant="ghost", size="md",
            icon_left=ui.avatar(variant="solid", initials=INITIALES[moi], size="xs",
                                color=COULEURS[moi]),
            icon_right="chevron-down",
            tooltip=tr("Who you are on this board",
                       "Qui tu es sur ce tableau"),
        ),
        align="end",
    ):
        for cle, nom, initiales, couleur in MEMBRES:
            ui.dropdown_item(
                label=nom,
                icon_left=ui.avatar(variant="solid", initials=initiales, size="xs",
                                    color=couleur),
                icon_right="check" if cle == moi else None,
                on_click=partial(devenir, cle),
            )


def connexion() -> None:
    """The real-time stream's state, bound — so with no zone to refresh.

    Making it a ``@refreshable`` zone would add HTML to every one of the
    responses it claims to describe.
    """
    live = LiveConnection()
    with ui.hstack(align="center", gap="xs", classes="shrink-0"):
        ui.icon("radio", color="success", size="sm", visible=live.connected,
                tooltip=tr("Live — your other windows follow",
                           "En direct — tes autres fenêtres suivent"))
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
        trigger=ui.icon_button("languages", variant="ghost", size="md",
                               tooltip=tr("Language", "Langue")),
        align="end",
    ):
        for cle, libelle in (("en", "English"), ("fr", "Français")):
            ui.dropdown_item(
                label=libelle,
                icon_right="check" if code.startswith(cle) else None,
                on_click=partial(Language.set, cle),
            )


def theme_sombre() -> None:
    """Light / dark, one button each and CSS shows the right one.

    Two buttons rather than one whose icon would depend on the scheme:
    the scheme lives in the browser, so the server cannot pick the icon.
    """
    ui.icon_button(
        "moon", variant="ghost", size="md",
        on_click=ColorScheme.toggle(),
        tooltip=tr("Switch to dark", "Passer en sombre"),
        classes="dark:!hidden",
    )
    ui.icon_button(
        "sun", variant="ghost", size="md",
        on_click=ColorScheme.toggle(),
        tooltip=tr("Switch to light", "Passer en clair"),
        classes="!hidden dark:!inline-flex",
    )


def dialogue_api() -> None:
    """This board's API: a ready command, and the reference.

    The routes, and why the key reaches THIS board:
    :mod:`examples.kanban.features.api`.

    Two shells, because a ``curl`` written for bash does not survive
    Windows PowerShell: there ``curl`` is another command, and its quoting
    eats the JSON. The PowerShell one is a table of parameters handed to
    ``Invoke-RestMethod``: short lines, no continuation character, so it
    pastes as it reads. The tab shown first follows the visitor's system.
    """
    requete = current_context().request
    origine = str(requete.base_url).rstrip("/")
    cle = auth.session_key()
    commandes = {
        "bash": f"""curl -X POST {origine}/api/cartes \\
  -H "Authorization: Bearer {cle}" \\
  -H "Content-Type: application/json" \\
  -d '{{"titre": "Hello from curl"}}'""",
        "powershell": f"""$request = @{{
  Method      = "Post"
  Uri         = "{origine}/api/cartes"
  Headers     = @{{ Authorization = "Bearer {cle}" }}
  ContentType = "application/json"
  Body        = '{{"titre": "Hello from PowerShell"}}'
}}
Invoke-RestMethod @request""",
    }
    windows = "Windows" in requete.headers.get("user-agent", "")
    boite = ui.dialog(title=tr("This board's API", "L'API de ce tableau"),
                      width="lg")
    with boite, ui.vstack(gap="md"):
        ui.text(tr("Run this command in a terminal: the card lands on THIS "
                   "board, and the windows you have open follow, live.",
                   "Lance cette commande dans un terminal : la carte arrive "
                   "sur CE tableau, et tes fenêtres ouvertes suivent, en "
                   "direct."), tag="p")
        with ui.tabs(value="powershell" if windows else "bash",
                     name="shell_api", size="sm"):
            ui.tab("bash", label="bash")
            ui.tab("powershell", label="PowerShell")
            for langage, commande in commandes.items():
                with ui.tab_panel(langage), ui.vstack(gap="sm",
                                                      classes="pt-3"):
                    ui.code(commande, lang=langage)
                    with ui.hstack(justify="end"):
                        ui.button(tr("Copy the command",
                                     "Copier la commande"),
                                  icon_left="copy", variant="soft",
                                  on_click=copy(commande))
        ui.link(tr("Every route, to try in the browser",
                   "Toutes les routes, à essayer dans le navigateur"),
                href="/docs", external=True)
        ui.text(tr("The key opens your session: your board, nobody else's. "
                   "Keep it to yourself.",
                   "La clé ouvre ta session : ton tableau, celui de "
                   "personne d'autre. Garde-la pour toi."),
                size="sm", color="muted", tag="p")
    ui.icon_button("code", variant="ghost", size="md",
                   tooltip=tr("API", "API"), on_click=boite.open())


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
              size="md", icon_left="plus", on_click=boite.open())


@refreshable(deps=[Tableau], broadcast=[Tableau])
def commandes() -> None:
    """Undo and redo. Their tooltips say WHAT they would undo.

    A zone because they describe the board: the number of possible undos
    changes with every write.

    Archiving has no button here: it acts on ONE card, so it lives with
    the card — the strip that appears under the board while one drags,
    and the drawer's button.
    """
    tableau = Tableau()
    with ui.hstack(align="center", gap="none", classes="shrink-0"):
        ui.icon_button(
            "undo-2", variant="ghost", size="md", on_click=annuler,
            disabled=tableau.curseur == 0,
            tooltip=(
                tr("Undo: ", "Annuler : ")
                + tableau.journal[tableau.curseur - 1]["texte"]
                if tableau.curseur
                else tr("Nothing to undo", "Rien à annuler")
            ),
        )
        ui.icon_button(
            "redo-2", variant="ghost", size="md", on_click=refaire,
            disabled=tableau.curseur >= len(tableau.journal),
            tooltip=(
                tr("Redo: ", "Rétablir : ")
                + tableau.journal[tableau.curseur]["texte"]
                if tableau.curseur < len(tableau.journal)
                else tr("Nothing to redo", "Rien à rétablir")
            ),
        )


def filtres_du_bandeau() -> None:
    """Search, assignee, label — the three server-side filters.

    The assignee is a row of avatars and not a list: on a board one
    recognises a face before a name, and the current filter stays in
    sight instead of folded into a closed select.
    """
    filtres = Filtres()
    # ``debounce`` on the field: one request per typing pause, not one
    # per character. The filtering is SERVER side here — cf.
    # ``state.Filtres``, which says why the mail client's client-side
    # filter would be a bug on a board whose cards get dragged.
    ui.input(
        value=filtres.q, on_input=filtrer, debounce=350,
        placeholder=tr("Search a card", "Rechercher une carte"),
        icon_left="search", size="md", clearable=True,
        classes="w-[15rem]",
    )
    with ui.toggle_group(value=filtres.qui, on_change=filtrer, size="md",
                         color="primary"):
        ui.toggle_button(value="tous", label=tr("All", "Tous"),
                         tooltip=tr("The whole team", "Toute l'équipe"))
        for cle, nom, initiales, couleur in MEMBRES:
            ui.toggle_button(
                value=cle,
                icon=ui.avatar(variant="solid", initials=initiales, size="xs", color=couleur),
                tooltip=tr(f"{nom}'s cards", f"Les cartes de {nom}"),
            )
    ui.select(
        value=filtres.etiquette, on_change=filtrer, size="md",
        classes="w-[9rem]",
        options=[("toutes", tr("All labels", "Toutes étiquettes")),
                 *[(cle, lib) for cle, lib, _ in ETIQUETTES]],
    )


#: The demo's head, in English like the default language: this is the
#: link people share, so it names the framework and says what to try.
TITLE = "Live Kanban demo — Bretzel, full-stack Python web framework"
DESCRIPTION = (
    "A shared Kanban board written in Python only with Bretzel: drag cards, "
    "undo, and watch a second browser window follow — no JavaScript to write."
)
SHARE_IMAGE = "https://bretzel-py.dev/assets/bretzel-mark.png"


@layout
def shell() -> None:
    ui.meta_tag(name="robots", content="index,follow,max-image-preview:large")
    ui.meta_tag(property="og:type", content="website")
    ui.meta_tag(property="og:site_name", content="Bretzel")
    ui.meta_tag(property="og:title", content=TITLE)
    ui.meta_tag(property="og:description", content=DESCRIPTION)
    ui.meta_tag(property="og:url", content="https://demo.bretzel-py.dev/")
    ui.meta_tag(property="og:image", content=SHARE_IMAGE)
    ui.meta_tag(name="twitter:card", content="summary")
    ui.meta_tag(name="twitter:image", content=SHARE_IMAGE)
    with ui.viewport(direction="col"):
        with ui.hstack(justify="between", align="center", gap="md",
                       wrap=True,
                       classes="shrink-0 px-5 py-4 border-b "
                               "border-text/10"):
            with ui.hstack(align="center", gap="lg", wrap=True):
                with ui.hstack(align="center", gap="sm", classes="shrink-0"):
                    with ui.hstack(align="center", justify="center",
                                   classes="bz-c-primary h-10 w-10 "
                                           "rounded-field bg-(--bz-solid) "
                                           "text-(--bz-on-solid)"):
                        ui.icon("kanban", size="md")
                    ui.heading(tr("Client portal rework",
                                  "Refonte du portail client"),
                               level=1, size="md", weight="semibold")
                    ui.badge("Sprint 24", variant="soft", color="primary",
                             size="md")
                with ui.hstack(align="center", gap="md", wrap=True):
                    filtres_du_bandeau()

            with ui.hstack(align="center", gap="sm", classes="shrink-0"):
                connexion()
                commandes()
                ui.divider(orientation="vertical", classes="h-6")
                theme_sombre()
                langue()
                dialogue_api()
                identite()
                dialogue_nouvelle()

        ui.outlet(classes="flex-1 min-h-0 flex")


feature = Feature(
    name="shell", kind="shell",
    provides=[shell, identite, connexion, langue, theme_sombre,
              dialogue_api, dialogue_nouvelle, commandes, filtres_du_bandeau],
    uses=["donnees", "state", "logic"],
)
