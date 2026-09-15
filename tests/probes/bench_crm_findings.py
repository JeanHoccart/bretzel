"""Bench : trois frictions relevées sur ``examples/crm`` (:8983).

Trois zones, trois hypothèses, chacune isolée du reste :

A. ``ui.calendar`` dans une zone ``@refreshable`` — un refresh qui NE
   change aucun attribut observé du ``<bz-calendar>`` (ici un bump
   affiché à côté) morphe sa grille de jours vers le conteneur VIDE que
   le SSR émet. ``connectedCallback`` ne re-tourne pas (le nœud survit),
   ``attributeChangedCallback`` non plus (rien n'a changé) : personne ne
   la re-remplit.

B. Une liste de ``ui.card`` dans un ``ui.vstack`` qui défile — la racine
   de ``card`` porte ``overflow-hidden``, donc sa taille minimale
   automatique de flex-item vaut 0 et rien ne pose ``shrink-0`` : les
   cartes s'écrasent sous leur contenu et le clippent. La MÊME carte
   hors du conteneur contraint sert de témoin.

C. ``ui.pagination`` cliqué vite — six clics « suivant » en 60 ms, une
   requête serveur par clic, et on regarde où atterrit la page.

Run :  py tests/probes/bench_crm_findings.py
"""

from __future__ import annotations

import asyncio

from bretzel import Bretzel, page, refreshable, ui
from bretzel.state import PageState, field
from bretzel.theme import ColorScheme

app = Bretzel(
    secret_key="dev-crm-findings-bench-secret-key",
    title="Bretzel · CRM findings bench",
    mode="dev",
)


class UI(PageState):
    bump: int = field(default=0)
    page: int = field(default=1)
    periode: list = field(default_factory=lambda: ["2026-07-20", "2026-08-19"])
    jour: str = field(default="2026-08-05")


def do_bump() -> None:
    UI().bump += 1


async def page_changed(state: UI) -> None:
    """La pagination hydrate ``page`` ; ``deps=`` re-render la zone.

    Le ``sleep`` copie le COÛT de la zone du CRM (une page de 20 000
    contacts se compte et se lit en base) : sans lui les réponses
    reviennent dans l'ordre où elles sont parties et aucun croisement
    n'est possible.
    """
    await asyncio.sleep(0.25)


@refreshable(deps=[UI])
def cal_zone() -> None:
    with ui.vstack(gap="sm", align="start"):
        ui.text(f"bump = {UI().bump}", id="bump")
        ui.calendar(value="2026-08-05", month="2026-08-05", weekstart=1,
                    size="sm", id="cal")


def range_changed(state: UI) -> None:
    """La période hydrate ``periode`` ; ``deps=`` re-render la zone."""


@refreshable(deps=[UI])
def range_zone() -> None:
    with ui.vstack(gap="sm", align="start"):
        ui.text(f"periode = {list(UI().periode)!r}", id="periode")
        ui.date_range_picker(value=UI().periode, size="sm",
                             on_change=range_changed, id="rng")
        # Le MÊME ``size`` que le picker : si les deux hauteurs diffèrent
        # ici, l'échelle ment ; si elles sont égales, c'est l'app qui a
        # mélangé les tailles.
        ui.select(["a", "b"], value="a", size="sm", id="sel")
        ui.text(f"jour = {UI().jour!r}", id="jour")
        ui.date_picker(value=UI().jour, on_change=range_changed, id="dp")


@refreshable(deps=[UI])
def pager_zone() -> None:
    with ui.vstack(gap="sm", align="start"):
        ui.text(f"page = {UI().page}", id="pageno")
        ui.pagination(value=UI().page, total_pages=50, max_visible=5,
                      size="sm", on_change=page_changed, id="pager")


def row(i: int) -> None:
    with ui.card(padding="sm"):
        with ui.hstack(gap="sm", align="center"):
            ui.avatar(initials="AB", size="sm")
            with ui.vstack(gap="none", classes="min-w-0 flex-1"):
                ui.text(f"Contact {i}", weight="medium", size="sm")
                ui.text("Compte de démonstration", color="muted", size="xs")


@page("/")
def home() -> None:
    with ui.vstack(gap="xl", classes="p-8"):
        ui.text("A. calendrier dans une zone", weight="bold")
        ui.button("bump (aucun attribut du calendrier ne change)",
                  on_click=do_bump, id="bumpbtn")
        cal_zone()

        ui.link("aller aux préférences", href="/prefs", id="toprefs")

        ui.text("D. période", weight="bold")
        range_zone()

        ui.text("C. pagination", weight="bold")
        pager_zone()

        ui.text("B. cartes dans un conteneur contraint", weight="bold")
        with ui.hstack(gap="lg", align="start"):
            # Le témoin : la MÊME carte, sans contrainte de hauteur.
            with ui.vstack(gap="xs", classes="w-72", id="free"):
                row(0)
            # Le cas : 25 cartes dans une colonne à hauteur fixe.
            # L'idiome COMPLET, celui que ``traps.md`` prescrit depuis le
            # 2026-08-21 : la quatrième classe, ``[&>*]:shrink-0``, est
            # celle qui empêche les cartes de se comprimer. Le finding
            # [26] a été tranché en doc + gate (pas de prop), donc ce banc
            # montre désormais la forme JUSTE — la forme fautive, elle,
            # est gardée par le témoin de
            # ``test_a_scrolling_column_does_not_crush_its_items``.
            with ui.vstack(gap="xs",
                           classes="w-72 h-[420px] min-h-0 overflow-y-auto "
                                   "[&>*]:shrink-0",
                           id="squeezed"):
                for i in range(1, 26):
                    row(i)


def save_prefs(**_) -> None:
    """Le formulaire de l'écran de paramètres, réduit à sa soumission."""


@refreshable(deps=[UI])
def theme_zone() -> None:
    """Le contrôle de thème DANS une zone et DANS un formulaire — la
    forme exacte de l'écran de paramètres du CRM."""
    with ui.form(on_submit=save_prefs):
        with ui.vstack(gap="md"):
            ui.text(f"bump = {UI().bump}", id="pbump")
            ui.toggle_group(value=ColorScheme().mode,
                            options=[("light", "Clair"), ("dark", "Sombre"),
                                     ("system", "Système")], id="theme")


@page("/prefs")
def prefs() -> None:
    """F. L'écran de préférences du CRM, réduit à son contrôle de thème :
    un ``toggle_group`` lié au ``ClientState`` du framework."""
    with ui.vstack(gap="md", classes="p-8"):
        ui.text("F. thème", weight="bold")
        ui.button("bump (refresh de la zone)", on_click=do_bump, id="pbumpbtn")
        theme_zone()


#: La coque du CRM, réduite à sa barre latérale : un titre, trois
#: sections, onze entrées, un pied. C'est le VOLUME qui compte — une
#: sidebar d'une entrée ne peut pas déborder de sa colonne.
NAV = [
    ("VENTES", [("Pipeline", "columns-3"), ("Comptes", "building-2"),
                ("Contacts", "users"), ("Activités", "calendar-days")]),
    ("PILOTAGE", [("Rapports", "bar-chart-3"), ("Recherche", "search"),
                  ("Temps réel", "radio")]),
    ("OUTILS", [("Import", "upload"), ("Paramètres", "settings"),
                ("Carte", "map"), ("Aide", "help-circle")]),
]


def moved(**_) -> None:
    """Le déplacement n'a rien à faire ici : ce qu'on mesure, c'est la
    CSS que le geste pose sur les cartes."""


@page("/kanban")
def kanban() -> None:
    """H. Une colonne de kanban : des cartes déplaçables qui défilent."""
    with ui.vstack(gap="md", classes="p-8"):
        ui.text("H. dnd tactile", weight="bold")
        with ui.dropzone(name="col", accepts=["deal"], on_move=moved,
                         id="col"):
            with ui.vstack(gap="xs",
                           classes="w-72 h-[300px] min-h-0 overflow-y-auto"):
                for i in range(12):
                    with ui.draggable(key=str(i), group="deal"):
                        with ui.card(padding="sm"):
                            ui.text(f"Affaire {i}", size="sm")


@page("/rail")
def rail() -> None:
    """G. La barre latérale repliée, au volume du CRM."""
    with ui.hstack(gap="none", align="stretch",
                   classes="fixed inset-0 w-full overflow-hidden"):
        with ui.sidebar(collapsible="rail", open=False, id="side"):
            ui.sidebar_title("Bretzel CRM",
                             icon=ui.icon("handshake", color="primary",
                                          size="lg"))
            for section, items in NAV:
                with ui.sidebar_section(label=section):
                    for label, icon in items:
                        ui.sidebar_item(label, icon=icon, href="/rail")
            with ui.sidebar_footer(name="Aïcha Benali", subtitle="Commercial"):
                ui.sidebar_footer_item(label="Se déconnecter",
                                       icon_left="log-out")
        with ui.vstack(gap="none", classes="flex-1 min-h-0 p-8"):
            ui.text("page", color="muted")


app.include(__name__)


if __name__ == "__main__":
    import uvicorn

    from tests.probes._serve import bench_port, use_local_tailwind

    # Le compilateur CSS depuis 127.0.0.1 et non depuis unpkg :

    # une suite ne doit pas dependre d'un tiers (cf. `_serve`).

    use_local_tailwind()


    uvicorn.run(app, host="127.0.0.1", port=bench_port(8983))
