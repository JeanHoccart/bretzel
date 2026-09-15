"""features/recherche — page : trouver un élève par son nom ou son prénom.

EF-C7 : *« recherche par nom ou prénom, sur toutes les classes de
l'année. Nom et prénom restent DISTINCTS : un élève qui s'appelle LEA de
son nom ne doit pas se confondre avec une Léa de prénom. »*

Cette dernière phrase est la seule chose difficile de l'écran, et elle se
joue dans le SQL (``eleves_data.chercher``) : les deux colonnes sont
comparées séparément. Un ``nom || prenom LIKE`` les fondrait, et « lea »
trouverait les deux — ce qui est peut-être pratique et n'est pas ce qui
est demandé.

⚠️ **La recherche est dans l'adresse** (EF-U1 : *« le tri d'une liste, la
recherche en cours »*). Un résultat se renvoie donc par lien, ce qui est
exactement le geste de quelqu'un qui cherche un élève pour quelqu'un
d'autre.
"""

from __future__ import annotations

from bretzel import Feature, page, refreshable, ui
from bretzel.state import PageState, field
from examples.ecole.features.annees import AnneeVue, annee_regardee
from examples.ecole.features.eleves_data import chercher
from examples.ecole.features.shell import shell

PATH = "/recherche"


class Recherche(PageState, addressable=True):
    """Ce qu'on cherche. ``q``, comme partout ailleurs sur le web."""

    q: str = field(default="", url="q")


def lancer(etat: Recherche) -> None:
    """Le corps est vide **et c'est le mécanisme** : le socle a hydraté
    ``etat.q`` avant l'appel, et la mutation seule re-rend la zone qui
    déclare ``deps=[Recherche]``. Le paramètre TYPÉ est ce qui hydrate —
    sans lui, le handler répondrait zéro octet."""


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
