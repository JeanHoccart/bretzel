"""features/contact_detail — écran 4 : la fiche d'un contact.

Ce que cet écran met sous contrainte : ``ui.tabs`` sur une page ROUTÉE par
paramètre de chemin, l'édition en ligne d'un enregistrement réel, et
``ui.file_upload`` dans un panneau étroit — le cas « composer » qui a déjà
cassé une fois.

C'est aussi la **première page à paramètre de chemin** des 18 apps : aucune
des 17 autres n'écrit ``@page("/x/{id}")``. Le mécanisme existe
(``server/routing/pages.py`` pose ``path_params``), il n'était simplement
jamais exercé par un exemple.
"""

from __future__ import annotations

from bretzel import Feature, abort, page, refreshable, ui
from bretzel.state import PageState, field, validator
from examples.crm.core.domain import (
    CONTACT_STATUS,
    STATUS_KEYS,
    TODAY,
    activity_badge,
    initials,
    status_badge,
)
from examples.crm.features.access import (
    ViewerPrefs,
    current_profile,
    visible_owner,
)
from examples.crm.features.contacts_data import (
    ContactsRev,
    add_note,
    contact_activities,
    contact_notes,
    get_contact,
    update_contact,
)
from examples.crm.features.shell import shell


class ContactSheet(PageState):
    """Quel contact la fiche montre, et le brouillon de son édition.

    L'id vit dans l'état plutôt que d'être relu du chemin à chaque zone : une
    zone ``@refreshable`` se re-render hors du routage, elle n'a aucun
    paramètre de chemin sous la main.
    """

    contact_id: int = field(default=0)
    first_name: str = field(default='')
    last_name: str = field(default='')
    email: str = field(default='')
    phone: str = field(default='')
    title: str = field(default='')
    status: str = field(default='active')

    @validator("status")
    def _status(cls, value: str) -> str:
        return value if value in STATUS_KEYS else "active"


class NoteDraft(PageState):
    body: str = field(default='')


def load_into(state: ContactSheet, contact: dict) -> None:
    """Recopie l'enregistrement dans le brouillon d'édition."""
    state.contact_id = contact["id"]
    state.first_name = contact["first_name"]
    state.last_name = contact["last_name"]
    state.email = contact["email"]
    state.phone = contact["phone"]
    state.title = contact["title"]
    state.status = contact["status"]


def save_contact(form: ContactSheet) -> None:
    """⚠️ ``form.contact_id`` n'est rendu par AUCUN champ, et arrive quand
    même du navigateur : c'est un attribut déclaré du ``PageState``, donc
    le socle l'hydrate depuis le corps du POST. Le cadrage vit dans
    ``update_contact``, pas ici — un appelant qui aurait à s'en souvenir
    finit par l'oublier."""
    if not form.contact_id:
        return
    saved = update_contact(int(form.contact_id), {
        "first_name": str(form.first_name).strip()[:60],
        "last_name": str(form.last_name).strip()[:60],
        "email": str(form.email).strip()[:120],
        "phone": str(form.phone).strip()[:30],
        "title": str(form.title).strip()[:80],
        "status": str(form.status),
    }, visible_owner())
    if not saved:
        ui.notification("Enregistrement refusé.", variant="error",
                        duration_ms=3000)
        return
    ui.notification("Fiche enregistrée", variant="success", duration_ms=2000)


def save_note(form: NoteDraft) -> None:
    body = str(form.body).strip()[:400]
    if not body:
        ui.notification("Une note vide ne s'enregistre pas.",
                        variant="warning", duration_ms=2000)
        return
    sheet = ContactSheet()
    if not sheet.contact_id:
        return
    # L'auteur est la personne CONNECTÉE. C'était ``OWNERS[0]`` en dur —
    # inoffensif tant que l'app n'avait pas d'identité, une fausse
    # attribution écrite en base dès qu'elle en a une.
    profile = current_profile()
    author = profile["display_name"] if profile else ""
    if not add_note(int(sheet.contact_id), body, author, TODAY.isoformat(),
                    visible_owner()):
        ui.notification("Note refusée.", variant="error", duration_ms=3000)
        return
    form.body = ""
    ui.notification("Note ajoutée", variant="success", duration_ms=2000)


@refreshable(deps=[ContactSheet, ContactsRev])
def identity_form() -> None:
    form = ContactSheet()
    with ui.form(on_submit=save_contact):
        with ui.vstack(gap="md"):
            with ui.grid(cols={"base": 1, "md": 2}, gap="md"):
                with ui.form_field(label="Prénom", required=True):
                    ui.input(value=form.first_name, maxlength=60,
                             icon_left="user")
                with ui.form_field(label="Nom", required=True):
                    ui.input(value=form.last_name, maxlength=60)
                with ui.form_field(label="Email", required=True):
                    ui.input(value=form.email, type="email", icon_left="mail")
                with ui.form_field(label="Téléphone"):
                    ui.input(value=form.phone, icon_left="phone")
                with ui.form_field(label="Fonction"):
                    ui.input(value=form.title, maxlength=80,
                             icon_left="briefcase")
                with ui.form_field(label="Statut"):
                    ui.select(
                        value=form.status,
                        options=[(k, lbl)
                                 for k, (lbl, _c) in CONTACT_STATUS.items()],
                    )
            with ui.hstack(justify="end"):
                ui.button("Enregistrer", type="submit", color="primary",
                          icon_left="save")


@refreshable(deps=[ContactSheet, ContactsRev])
def activity_feed() -> None:
    sheet = ContactSheet()
    activities = contact_activities(int(sheet.contact_id), limit=25)
    notes = contact_notes(int(sheet.contact_id), limit=10)
    with ui.vstack(gap="lg"):
        with ui.vstack(gap="sm"):
            ui.heading("Historique", level=3, size="sm")
            if not activities:
                ui.text("Aucune activité enregistrée.", color="muted",
                        size="sm")
            for activity in ui.each(activities, key="id"):
                label, icon, color = activity_badge(activity["kind"])
                with ui.card(padding="sm"):
                    with ui.hstack(gap="sm", align="center"):
                        ui.icon(icon, color=color, size="sm")
                        with ui.vstack(gap="none", classes="min-w-0 flex-1"):
                            ui.text(activity["subject"], size="sm",
                                    weight="medium", truncate=True)
                            ui.text(f"{label} · {activity['owner']}",
                                    color="muted", size="xs")
                        ui.text(activity["at"], color="muted", size="xs")
        ui.divider(label="Notes")
        with ui.vstack(gap="sm"):
            for note in ui.each(notes, key="id"):
                with ui.vstack(gap="none"):
                    ui.text(note["body"], size="sm")
                    ui.text(f"{note['author']} · {note['at']}", color="muted",
                            size="xs")
            note_form()


# Les trois, et pas seulement ``NoteDraft`` : cette zone est appelée
# DANS ``activity_feed``, donc elle repart avec lui à chaque fois. Une
# zone imbriquée qui déclare moins que son conteneur ment sur ses
# propres re-rendus — ici le formulaire est inline, il a sa place dans
# le flux du fil, et c'est la déclaration qui se met à jour.
@refreshable(deps=[NoteDraft, ContactSheet, ContactsRev])
def note_form() -> None:
    draft = NoteDraft()
    with ui.form(on_submit=save_note):
        with ui.vstack(gap="sm"):
            ui.textarea(value=draft.body, rows=3,
                        placeholder="Ajouter une note…", maxlength=400)
            with ui.hstack(justify="end"):
                ui.button("Ajouter la note", type="submit", size="sm",
                          variant="soft", icon_left="plus")


def documents_tab() -> None:
    """``file_upload`` dans une colonne étroite — le cas « composer ».

    Le panneau fait un tiers de la page ; c'est exactement la boîte dans
    laquelle la variante ``dropzone`` avait déjà débordé.
    """
    with ui.grid(cols={"base": 1, "lg": 3}, gap="lg"):
        with ui.vstack(gap="md"):
            ui.heading("Déposer un document", level=3, size="sm")
            ui.file_upload(
                variant="dropzone", list="chips", multiple=True, max_files=5,
                max_size_mb=8, accept=[".pdf", ".png", ".jpg", ".docx"],
                label="Contrat, devis, compte rendu…",
            )
        with ui.vstack(gap="md"):
            ui.heading("Bouton compact", level=3, size="sm")
            ui.file_upload(variant="button", list="chips", multiple=True,
                           max_files=3, label="Joindre")
        with ui.vstack(gap="md"):
            ui.heading("Rappel", level=3, size="sm")
            ui.text(
                "Aucun stockage n'est branché : cet onglet mesure la tenue "
                "du composant dans une colonne étroite, pas un envoi.",
                color="muted", size="sm",
            )


@refreshable(deps=[ContactSheet, ContactsRev, ViewerPrefs])
def sheet_header() -> None:
    sheet = ContactSheet()
    contact = get_contact(int(sheet.contact_id), visible_owner())
    if contact is None:
        return
    label, color = status_badge(contact["status"])
    with ui.hstack(gap="md", align="center", wrap=True):
        ui.avatar(
            initials=initials(contact["first_name"], contact["last_name"]),
            size="lg", color="primary",
        )
        with ui.vstack(gap="none", classes="min-w-0 flex-1"):
            ui.heading(f"{contact['first_name']} {contact['last_name']}",
                       level=1, size="xl")
            ui.text(f"{contact['title']} · {contact['account_name']} "
                    f"({contact['account_city']})",
                    color="muted", size="sm", truncate=True)
        ui.badge(label, color=color, variant="soft")


@page("/contacts/{contact_id}", layout=shell, title="Fiche contact")
def contact_sheet_page(contact_id: int) -> None:
    contact = get_contact(int(contact_id), visible_owner())
    if contact is None:
        abort(404)
    sheet = ContactSheet()
    # Le brouillon suit la fiche ouverte. Sans cette garde, revenir sur une
    # AUTRE fiche garderait l'édition en cours de la précédente — le
    # ``PageState`` survit à la navigation htmx.
    if int(sheet.contact_id) != int(contact["id"]):
        load_into(sheet, contact)

    with ui.vstack(gap="lg"):
        with ui.breadcrumb():
            ui.breadcrumb_item(label="Contacts", href="/contacts",
                               icon="users")
            ui.breadcrumb_item(
                label=f"{contact['first_name']} {contact['last_name']}")
        sheet_header()
        # ``url=`` : l'onglet ouvert vit dans l'adresse, donc
        # ``/contacts/12?onglet=activity`` s'ouvre sur les activités chez
        # qui reçoit le lien. Le clic reste instantané — aucune requête,
        # c'est ``bz-show`` qui bascule un panneau déjà monté.
        with ui.tabs(value="identity", url="onglet"):
            ui.tab("identity", label="Identité", icon="id-card")
            ui.tab("activity", label="Activités", icon="history")
            ui.tab("documents", label="Documents", icon="paperclip")
            with ui.tab_panel(tab="identity"):
                identity_form()
            with ui.tab_panel(tab="activity"):
                activity_feed()
            with ui.tab_panel(tab="documents"):
                documents_tab()


feature = Feature(
    name="contact_detail",
    kind="page",
    provides=[contact_sheet_page, ContactSheet, NoteDraft],
    uses=["access", "contacts_data"],
)
