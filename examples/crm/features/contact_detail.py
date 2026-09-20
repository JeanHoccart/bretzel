"""features/contact_detail — screen 4: a contact's sheet.

What this screen puts under constraint: ``ui.tabs`` on a page ROUTED by a
path parameter, in-line editing of a real record, and ``ui.file_upload``
in a narrow panel — the "composer" case that has broken once already.

It is also the 18 apps' **first path-parameter page**: none of the other
17 writes ``@page("/x/{id}")``. The mechanism exists
(``server/routing/pages.py`` sets ``path_params``), it simply was never
exercised by an example.
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
    """Which contact the sheet shows, and the draft of its editing.

    The id lives in the state rather than being re-read from the path at
    every zone: a ``@refreshable`` zone re-renders outside the routing,
    it has no path parameter at hand.
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
    """Copy the record into the editing draft."""
    state.contact_id = contact["id"]
    state.first_name = contact["first_name"]
    state.last_name = contact["last_name"]
    state.email = contact["email"]
    state.phone = contact["phone"]
    state.title = contact["title"]
    state.status = contact["status"]


def save_contact(form: ContactSheet) -> None:
    """⚠️ ``form.contact_id`` is rendered by NO field, and arrives from
    the browser anyway: it is a declared attribute of the ``PageState``,
    so the base layer hydrates it from the POST body. The scoping lives
    in ``update_contact``, not here — a caller that had to remember it
    ends up forgetting."""
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
        ui.notification("Save refused.", variant="error",
                        duration_ms=3000)
        return
    ui.notification("Sheet saved", variant="success", duration_ms=2000)


def save_note(form: NoteDraft) -> None:
    body = str(form.body).strip()[:400]
    if not body:
        ui.notification("An empty note does not get saved.",
                        variant="warning", duration_ms=2000)
        return
    sheet = ContactSheet()
    if not sheet.contact_id:
        return
    # The author is the SIGNED-IN person. It was ``OWNERS[0]``
    # hard-coded — harmless as long as the app had no identity, a false
    # attribution written into the database as soon as it has one.
    profile = current_profile()
    author = profile["display_name"] if profile else ""
    if not add_note(int(sheet.contact_id), body, author, TODAY.isoformat(),
                    visible_owner()):
        ui.notification("Note refused.", variant="error", duration_ms=3000)
        return
    form.body = ""
    ui.notification("Note added", variant="success", duration_ms=2000)


@refreshable(deps=[ContactSheet, ContactsRev])
def identity_form() -> None:
    form = ContactSheet()
    with ui.form(on_submit=save_contact):
        with ui.vstack(gap="md"):
            with ui.grid(cols={"base": 1, "md": 2}, gap="md"):
                with ui.form_field(label="First name", required=True):
                    ui.input(value=form.first_name, maxlength=60,
                             icon_left="user")
                with ui.form_field(label="Last name", required=True):
                    ui.input(value=form.last_name, maxlength=60)
                with ui.form_field(label="Email", required=True):
                    ui.input(value=form.email, type="email", icon_left="mail")
                with ui.form_field(label="Phone"):
                    ui.input(value=form.phone, icon_left="phone")
                with ui.form_field(label="Job title"):
                    ui.input(value=form.title, maxlength=80,
                             icon_left="briefcase")
                with ui.form_field(label="Status"):
                    ui.select(
                        value=form.status,
                        options=[(k, lbl)
                                 for k, (lbl, _c) in CONTACT_STATUS.items()],
                    )
            with ui.hstack(justify="end"):
                ui.button("Save", type="submit", color="primary",
                          icon_left="save")


@refreshable(deps=[ContactSheet, ContactsRev])
def activity_feed() -> None:
    sheet = ContactSheet()
    activities = contact_activities(int(sheet.contact_id), limit=25)
    notes = contact_notes(int(sheet.contact_id), limit=10)
    with ui.vstack(gap="lg"):
        with ui.vstack(gap="sm"):
            ui.heading("History", level=3, size="sm")
            if not activities:
                ui.text("No activity recorded.", color="muted",
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


# All three, and not only ``NoteDraft``: this zone is called INSIDE
# ``activity_feed``, so it goes out with it every time. A nested zone
# declaring less than its container lies about its own re-renders — here
# the form is inline, it belongs in the feed's flow, and it is the
# declaration that gets updated.
@refreshable(deps=[NoteDraft, ContactSheet, ContactsRev])
def note_form() -> None:
    draft = NoteDraft()
    with ui.form(on_submit=save_note):
        with ui.vstack(gap="sm"):
            ui.textarea(value=draft.body, rows=3,
                        placeholder="Add a note…", maxlength=400)
            with ui.hstack(justify="end"):
                ui.button("Add the note", type="submit", size="sm",
                          variant="soft", icon_left="plus")


def documents_tab() -> None:
    """``file_upload`` in a narrow column — the "composer" case.

    The panel is a third of the page; it is exactly the box in which the
    ``dropzone`` variant had already overflowed.
    """
    with ui.grid(cols={"base": 1, "lg": 3}, gap="lg"):
        with ui.vstack(gap="md"):
            ui.heading("Drop a document", level=3, size="sm")
            ui.file_upload(
                variant="dropzone", list="chips", multiple=True, max_files=5,
                max_size_mb=8, accept=[".pdf", ".png", ".jpg", ".docx"],
                label="Contract, quote, minutes…",
            )
        with ui.vstack(gap="md"):
            ui.heading("Compact button", level=3, size="sm")
            ui.file_upload(variant="button", list="chips", multiple=True,
                           max_files=3, label="Attach")
        with ui.vstack(gap="md"):
            ui.heading("Reminder", level=3, size="sm")
            ui.text(
                "No storage is wired: this tab measures how the "
                "component holds up in a narrow column, not an upload.",
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


@page("/contacts/{contact_id}", layout=shell, title="Contact sheet")
def contact_sheet_page(contact_id: int) -> None:
    contact = get_contact(int(contact_id), visible_owner())
    if contact is None:
        abort(404)
    sheet = ContactSheet()
    # The draft follows the open sheet. Without this guard, coming back
    # to ANOTHER sheet would keep the previous one's editing in progress
    # — the ``PageState`` survives htmx navigation.
    if int(sheet.contact_id) != int(contact["id"]):
        load_into(sheet, contact)

    with ui.vstack(gap="lg"):
        with ui.breadcrumb():
            ui.breadcrumb_item(label="Contacts", href="/contacts",
                               icon="users")
            ui.breadcrumb_item(
                label=f"{contact['first_name']} {contact['last_name']}")
        sheet_header()
        # ``url=``: the open tab lives in the address, so
        # ``/contacts/12?onglet=activity`` opens on the activities for
        # whoever receives the link. The click stays instant — no
        # request, it is ``bz-show`` that flips an already-mounted panel.
        with ui.tabs(value="identity", url="onglet"):
            ui.tab("identity", label="Identity", icon="id-card")
            ui.tab("activity", label="Activities", icon="history")
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
