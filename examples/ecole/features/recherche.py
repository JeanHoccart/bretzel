"""features/recherche — page: find a pupil by surname or first name.

EF-C7: *"search by surname or first name, across every class of the
year. Surname and first name stay DISTINCT: a pupil whose surname is LEA
must not be confused with a Léa by first name."*

That last sentence is the only hard thing on the screen, and it is played
out in the SQL (``eleves_data.chercher``): the two columns are compared
separately. A ``nom || prenom LIKE`` would merge them, and "lea" would
find both — which may be convenient and is not what is asked for.

⚠️ **The search is in the address** (EF-U1: *"a list's sort, the search
in progress"*). A result is therefore sent back by link, which is exactly
the gesture of somebody looking up a pupil for somebody else.
"""

from __future__ import annotations

from bretzel import Feature, page, refreshable, ui
from bretzel.state import PageState, field
from examples.ecole.features.annees import AnneeVue, annee_regardee
from examples.ecole.features.eleves_data import chercher
from examples.ecole.features.shell import shell

PATH = "/recherche"


class Recherche(PageState, addressable=True):
    """What is being searched for. ``q``, as everywhere else on the web."""

    q: str = field(default="", url="q")


def lancer(etat: Recherche) -> None:
    """The body is empty **and that is the mechanism**: the base layer
    hydrated ``etat.q`` before the call, and the mutation alone
    re-renders the zone declaring ``deps=[Recherche]``. The TYPED
    parameter is what hydrates — without it, the handler would answer
    zero bytes."""


@refreshable(deps=[AnneeVue, Recherche])
def resultats() -> None:
    etat = Recherche()
    annee = annee_regardee()
    texte = str(etat.q).strip()
    trouves = chercher(annee["id"], texte)

    with ui.vstack(gap="md"):
        with ui.form(on_submit=lancer), ui.hstack(gap="md", align="end", wrap=True):
            with ui.form_field(
                label="Nom ou prénom",
                hint=f"Sur toutes les classes de {annee['libelle']}.",
            ):
                ui.input(value=etat.q, icon_left="search",
                         placeholder="Courty, Léane…")
            ui.button("Chercher", type="submit", color="primary",
                      icon_left="search")

        if not texte:
            ui.empty_state(
                title="Tapez un nom ou un prénom",
                icon="search",
                description="Les deux champs restent distincts : chercher "
                            "« Léa » ne rend pas les élèves dont c'est le "
                            "nom de famille.",
            )
            return
        if not trouves:
            ui.empty_state(title=f"Aucun élève pour « {texte} »",
                           icon="search-x")
            return

        ui.text(f"{len(trouves)} élève(s)", color="muted")
        with ui.grid(min_col="16rem", gap="md"):
            for ligne in ui.each(trouves, key="id"):
                with (
                    ui.card(padding="sm",
                            href=f"/eleve/{ligne['id']}"),
                    ui.hstack(gap="md", align="center"),
                ):
                    ui.avatar(
                        name=f"{ligne['prenom']} {ligne['nom']}",
                        size="lg", shape="circle")
                    with ui.vstack(gap="none"):
                        ui.text(ligne["nom"].upper(), weight="semibold")
                        ui.text(ligne["prenom"], color="muted")
                    ui.badge(label=ligne["code"], variant="outline",
                             size="xl")


@page(PATH, layout=shell, title="Recherche")
def recherche_page() -> None:
    with ui.vstack(gap="lg"):
        ui.heading("Chercher un élève", level=1, size="2xl")
        resultats()


feature = Feature(
    name="recherche",
    kind="page",
    provides=[recherche_page, Recherche],
    uses=["eleves_data", "annees", "shell"],
)
