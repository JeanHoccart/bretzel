"""features/contacts — écran 3 : maître-détail, et la SÉLECTION.

Ce que cet écran met sous contrainte, et qu'aucune des 17 apps ne construit :
une **liste sélectionnable**. Cliquer une ligne ne navigue pas — elle marque
un choix, la ligne le montre, et un panneau voisin suit.

La coque deux colonnes est un ``ui.resizable`` : c'est le seul composant du
catalogue qui exprime « deux panneaux et une poignée entre eux ». ``ui.grid``
ne sait pas donner deux tiers à l'un de ses enfants — il n'a pas de portée de
colonne.

Les deux panneaux sont **deux zones distinctes**, et le ``resizable`` vit en
dehors des deux : une largeur qu'on vient de tirer à la main ne doit pas
être rejouée par le serveur au premier clic de sélection.
"""

from __future__ import annotations

import math
from functools import partial

from bretzel import Feature, page, refreshable, ui
from bretzel.state import PageState, field, validator
from examples.crm.core.domain import (
    CONTACT_STATUS,
    STATUS_KEYS,
    initials,
    status_badge,
)
from examples.crm.features.access import ViewerPrefs, visible_owner
from examples.crm.features.contacts_data import (
    ContactsRev,
    contact_activities,
    get_contact,
    search_contacts,
)
from examples.crm.features.settings import Preferences
from examples.crm.features.shell import shell


class ContactsUI(PageState):
    """Ce que le lecteur regarde : son filtre, sa page, et son CHOIX."""

    needle: str = field(default='')
    status: str = field(default='all')
    page: int = field(default=1)
    #: 0 = rien de sélectionné. Le panneau de droite le lit ; c'est tout
    #: l'état que la sélection demande.
    selected_id: int = field(default=0)

    @validator("status")
    def _status(cls, value: str) -> str:
        return value if value in STATUS_KEYS else "all"

    @validator("page")
    def _page(cls, value: int) -> int:
        return max(1, int(value or 1))


def filter_changed(state: ContactsUI) -> None:
    """Un filtre qui bouge remet à la page 1 : rester page 7 d'une liste
    qu'on vient de restreindre montre des lignes que personne n'a demandées."""
    state.page = 1


def page_changed(state: ContactsUI) -> None:
    """La pagination hydrate ``page`` ; la zone se re-render par ``deps=``."""


def select_contact(contact_id: int) -> None:
    ContactsUI().selected_id = contact_id


def contact_row(contact: dict, selected: bool) -> None:
    """Une ligne sélectionnable — l'état choisi ne tient qu'à des props.

    ``color="primary"`` sur la carte sélectionnée avait été ESSAYÉ d'abord
    et retiré : ``ui.card`` peignait ``bg-{bg_color}`` sans jamais poser
    ``text-{fg_color}``, donc fond teal foncé et texte sombre — contraste
    mesuré à 3,12, sous le seuil AA. C'était le finding [3] du chantier ;
    il est **réparé depuis le 2026-08-21** (contraste 5,21), et le signal
    fort revient donc ici. Le contournement qui vivait à sa place — une
    surface ``interface`` plus deux accents — est parti avec lui, et c'est
    ça la preuve que la réparation sert.
    """
    with ui.card(padding="sm", hoverable=True,
                 color="primary" if selected else None,
                 on_click=partial(select_contact, contact["id"])):
        with ui.hstack(gap="sm", align="center"):
            ui.avatar(
                initials=initials(contact["first_name"], contact["last_name"]),
                size="sm",
                color="muted",
            )
            with ui.vstack(gap="none", classes="min-w-0 flex-1"):
                ui.text(f"{contact['first_name']} {contact['last_name']}",
                        weight="semibold" if selected else "medium", size="sm",
                        truncate=True)
                ui.text(contact["account_name"],
                        color=None if selected else "muted", size="xs",
                        truncate=True)
            label, color = status_badge(contact["status"])
            ui.badge(label, color=color, variant="soft", size="xs")


# ``ViewerPrefs`` dans les ``deps`` : sans lui, changer de portefeuille
# dans la barre latérale laisserait la zone sur la donnée de l'ancien.
@refreshable(deps=[ContactsUI, ContactsRev, ViewerPrefs])
def contact_list() -> None:
    state = ContactsUI()
    # Le réglage de l'écran 10 est LU ici. Sans ce fil, « Lignes par page »
    # serait un contrôle qui ne commande rien — et une page de paramètres
    # dont aucun réglage n'agit est une maquette, pas un écran.
    per_page = max(1, int(Preferences().par_page))
    rows, total = search_contacts(
        state.needle, state.status, int(state.page), per_page,
        visible_owner(),
    )
    pages = max(1, math.ceil(total / per_page))
    with ui.vstack(gap="sm", classes="h-full min-h-0"):
        with ui.hstack(justify="between", align="center"):
            ui.text(f"{total} contacts", color="muted", size="sm")
            ui.text(f"page {state.page} / {pages}", color="muted", size="xs")
        # ``ui.pane`` porte les quatre classes de l'idiome, dont la
        # quatrième — ``[&>*]:shrink-0`` — qui ne se devine pas : la racine
        # de ``ui.card`` clippe, donc sa hauteur minimale automatique vaut
        # ZÉRO et les cartes se compriment sous leur contenu dès que la
        # liste remplit la colonne. Mesuré ICI avant que le composant
        # existe : 73 px libre contre 34 px contraint, 39 px coupés, et
        # invisible sur la dernière page faute de lignes.
        with ui.pane(gap="xs", classes="pr-1"):
            if rows:
                for contact in ui.each(rows, key="id"):
                    contact_row(contact, contact["id"] == state.selected_id)
            else:
                ui.empty_state("Aucun contact", icon="user-x",
                               description="Ajuste la recherche ou le statut.")
        ui.pagination(value=state.page, total_pages=pages, max_visible=5,
                      size="sm", on_change=page_changed)


@refreshable(deps=[ContactsUI, ContactsRev, ViewerPrefs])
def contact_panel() -> None:
    state = ContactsUI()
    contact = (get_contact(int(state.selected_id), visible_owner())
               if state.selected_id else None)
    if contact is None:
        ui.empty_state(
            "Aucun contact sélectionné", icon="mouse-pointer-click",
            description="Choisis un contact à gauche pour voir sa fiche.",
        )
        return

    label, color = status_badge(contact["status"])
    with ui.pane(gap="lg", classes="pr-1"):
        with ui.hstack(gap="md", align="center"):
            ui.avatar(
                initials=initials(contact["first_name"], contact["last_name"]),
                size="lg", color="primary",
            )
            with ui.vstack(gap="none", classes="min-w-0 flex-1"):
                ui.heading(f"{contact['first_name']} {contact['last_name']}",
                           level=2, size="lg")
                ui.text(f"{contact['title']} · {contact['account_name']}",
                        color="muted", size="sm", truncate=True)
            ui.badge(label, color=color, variant="soft")
            # ``variant="underline"`` et pas un bouton : ``ui.link`` n'offre
            # que trois variantes de TEXTE (hover / text / underline), et
            # ``ui.button`` n'a pas de ``href=``. Un appel à l'action qui
            # navigue n'a donc pas de forme dans le catalogue.
            ui.link("Ouvrir la fiche", href=f"/contacts/{contact['id']}",
                    variant="underline", color="primary")

        with ui.grid(cols={"base": 1, "sm": 2}, gap="md"):
            for icon, value in (
                ("mail", contact["email"]),
                ("phone", contact["phone"]),
                ("building-2", f"{contact['account_name']} · "
                               f"{contact['account_city']}"),
                ("calendar", f"Client depuis le {contact['created_at']}"),
            ):
                with ui.hstack(gap="sm", align="center"):
                    ui.icon(icon, color="muted", size="sm")
                    ui.text(value, size="sm", truncate=True)

        ui.divider(label="Dernières activités")
        activities = contact_activities(contact["id"], limit=6)
        if activities:
            for activity in ui.each(activities, key="id"):
                with ui.hstack(gap="sm", align="center"):
                    ui.text(activity["at"], color="muted", size="xs")
                    ui.text(activity["subject"], size="sm", truncate=True)
        else:
            ui.text("Rien d'enregistré pour ce contact.", color="muted",
                    size="sm")


def filter_bar() -> None:
    # ``ui.grid`` et non ``ui.hstack`` : la racine d'un ``ui.form_field`` est
    # ``w-full``, donc dans une rangée flex chaque champ prend la largeur
    # entière et le suivant passe à la ligne. Une grille donne une colonne
    # bornée à chacun, sans avoir à poser de classe.
    state = ContactsUI()
    with ui.grid(cols={"base": 1, "md": 3}, gap="md"):
        with ui.form_field(label="Recherche"):
            ui.input(value=state.needle, placeholder="Nom, email, compte…",
                     icon_left="search", clearable=True,
                     on_change=filter_changed, debounce=300)
        with ui.form_field(label="Statut"):
            ui.select(
                value=state.status,
                options=[("all", "Tous les statuts"),
                         *[(k, lbl) for k, (lbl, _c) in CONTACT_STATUS.items()]],
                on_change=filter_changed,
            )


@page("/contacts", layout=shell, title="Contacts")
def contacts_page() -> None:
    with ui.vstack(gap="lg"):
        ui.heading("Contacts", level=1, size="2xl")
        filter_bar()
        # Le groupe redimensionnable a besoin d'une hauteur : dans un flux
        # vertical, ses panneaux n'en ont aucune à hériter.
        # Une hauteur EXPLICITE, pas ``flex-1`` : dans un flux vertical,
        # ``flex-1`` grandit avec son contenu tant que le parent n'a pas de
        # hauteur, et la liste débordait sous le pied de page. Mesuré : la
        # pagination sortait du viewport.
        with ui.resizable(sizes=[34, 66], orientation="horizontal",
                          gap="md", name="contacts_split",
                          classes="h-[calc(100vh-14rem)]"):
            # ⚠️ Les DEUX panneaux sont habillés pareil, et c'est le
            # finding [28]. ``ui.resizable_panel`` n'a aucun padding — il
            # ne rend aucune classe à lui, c'est écrit et assumé — donc
            # celui de gauche collait au bord de la fenêtre ET à la
            # poignée, pendant que celui de droite avait l'air correct
            # PAR ACCIDENT : sa ``ui.card`` apportait le sien.
            #
            # La réponse n'est pas un ``padding=`` sur le panneau : ce
            # serait du vocabulaire propriétaire pour ce que du Tailwind
            # standard écrit déjà, et ``ui.card`` est le seul composant
            # du catalogue à exposer cette échelle. C'est l'app qui
            # décide de sa respiration.
            #
            # Le ``gap="md"`` du groupe, lui, est du framework de plein
            # droit et fait l'autre moitié : les cartes touchaient la
            # poignée (2 px entre les deux surfaces), parce qu'aucun
            # padding d'ancêtre ne peut créer d'espace À L'INTÉRIEUR du
            # groupe. Seul le parent des panneaux sait où est la poignée.
            with ui.resizable_panel(min_size=22):
                with ui.card(padding="md", classes="h-full min-h-0"):
                    contact_list()
            with ui.resizable_panel(min_size=40):
                with ui.card(padding="md", classes="h-full min-h-0"):
                    contact_panel()


feature = Feature(
    name="contacts",
    kind="page",
    provides=[contacts_page, ContactsUI, select_contact],
    uses=["contacts_data", "settings", "access"],
)
