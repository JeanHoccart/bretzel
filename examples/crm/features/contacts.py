"""features/contacts — screen 3: master-detail, and SELECTION.

What this screen puts under constraint, and that none of the 17 apps
builds: a **selectable list**. Clicking a row does not navigate — it
marks a choice, the row shows it, and a neighbouring panel follows.

The two-column shell is a ``ui.resizable``: it is the catalogue's only
component expressing "two panels and a handle between them". ``ui.grid``
cannot give two thirds to one of its children — it has no column span.

The two panels are **two distinct zones**, and the ``resizable`` lives
outside both: a width one has just dragged by hand must not be replayed
by the server at the first selection click.
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
    """What the reader is looking at: their filter, their page, and their
    CHOICE."""

    needle: str = field(default='')
    status: str = field(default='all')
    page: int = field(default=1)
    #: 0 = nothing selected. The right panel reads it; it is all the
    #: state the selection needs.
    selected_id: int = field(default=0)

    @validator("status")
    def _status(cls, value: str) -> str:
        return value if value in STATUS_KEYS else "all"

    @validator("page")
    def _page(cls, value: int) -> int:
        return max(1, int(value or 1))


def filter_changed(state: ContactsUI) -> None:
    """A filter that moves resets to page 1: staying on page 7 of a list
    one has just narrowed shows rows nobody asked for."""
    state.page = 1


def page_changed(state: ContactsUI) -> None:
    """The pagination hydrates ``page``; the zone re-renders through
    ``deps=``."""


def select_contact(contact_id: int) -> None:
    ContactsUI().selected_id = contact_id


def contact_row(contact: dict, selected: bool) -> None:
    """A selectable row — the chosen state hangs on props alone.

    ``color="primary"`` on the selected card was TRIED first and removed:
    ``ui.card`` painted ``bg-{bg_color}`` without ever setting
    ``text-{fg_color}``, hence a dark teal background and dark text —
    contrast measured at 3.12, below the AA threshold. It was the work's
    finding [3]; it has been **fixed since 2026-08-21** (contrast 5.21),
    so the strong signal comes back here. The workaround that lived in
    its place — an ``interface`` surface plus two accents — went with it,
    and that is the proof the fix serves.
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


# ``ViewerPrefs`` in the ``deps``: without it, changing portfolio in the
# sidebar would leave the zone on the previous one's data.
@refreshable(deps=[ContactsUI, ContactsRev, ViewerPrefs])
def contact_list() -> None:
    state = ContactsUI()
    # Screen 10's setting is READ here. Without this thread, "Lignes par
    # page" would be a control commanding nothing — and a settings page
    # where no setting acts is a mock-up, not a screen.
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
        # ``ui.pane`` carries the idiom's four classes, including the
        # fourth — ``[&>*]:shrink-0`` — which cannot be guessed:
        # ``ui.card``'s root clips, so its automatic minimum height is
        # ZERO and the cards compress under their content as soon as the
        # list fills the column. Measured HERE before the component
        # existed: 73 px free against 34 px constrained, 39 px cut, and
        # invisible on the last page for want of rows.
        with ui.pane(gap="xs", classes="pr-1"):
            if rows:
                for contact in ui.each(rows, key="id"):
                    contact_row(contact, contact["id"] == state.selected_id)
            else:
                ui.empty_state("Aucun contact", icon="user-x",
                               description="Adjust the search or the status.")
        ui.pagination(value=state.page, total_pages=pages, max_visible=5,
                      size="sm", on_change=page_changed)


@refreshable(deps=[ContactsUI, ContactsRev, ViewerPrefs])
def contact_panel() -> None:
    state = ContactsUI()
    contact = (get_contact(int(state.selected_id), visible_owner())
               if state.selected_id else None)
    if contact is None:
        ui.empty_state(
            "No contact selected", icon="mouse-pointer-click",
            description="Pick a contact on the left to see its sheet.",
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
            # ``variant="underline"`` and not a button: ``ui.link``
            # offers only three TEXT variants (hover / text / underline),
            # and ``ui.button`` has no ``href=``. A call to action that
            # navigates therefore has no shape in the catalogue.
            ui.link("Open the sheet", href=f"/contacts/{contact['id']}",
                    variant="underline", color="primary")

        with ui.grid(cols={"base": 1, "sm": 2}, gap="md"):
            for icon, value in (
                ("mail", contact["email"]),
                ("phone", contact["phone"]),
                ("building-2", f"{contact['account_name']} · "
                               f"{contact['account_city']}"),
                ("calendar", f"Customer since {contact['created_at']}"),
            ):
                with ui.hstack(gap="sm", align="center"):
                    ui.icon(icon, color="muted", size="sm")
                    ui.text(value, size="sm", truncate=True)

        ui.divider(label="Latest activities")
        activities = contact_activities(contact["id"], limit=6)
        if activities:
            for activity in ui.each(activities, key="id"):
                with ui.hstack(gap="sm", align="center"):
                    ui.text(activity["at"], color="muted", size="xs")
                    ui.text(activity["subject"], size="sm", truncate=True)
        else:
            ui.text("Nothing recorded for this contact.", color="muted",
                    size="sm")


def filter_bar() -> None:
    # ``ui.grid`` and not ``ui.hstack``: a ``ui.form_field``'s root is
    # ``w-full``, so in a flex row each field takes the whole width and
    # the next wraps. A grid gives each a bounded column, without having
    # to set a class.
    state = ContactsUI()
    with ui.grid(cols={"base": 1, "md": 3}, gap="md"):
        with ui.form_field(label="Search"):
            ui.input(value=state.needle, placeholder="Name, email, account…",
                     icon_left="search", clearable=True,
                     on_change=filter_changed, debounce=300)
        with ui.form_field(label="Status"):
            ui.select(
                value=state.status,
                options=[("all", "Every status"),
                         *[(k, lbl) for k, (lbl, _c) in CONTACT_STATUS.items()]],
                on_change=filter_changed,
            )


@page("/contacts", layout=shell, title="Contacts")
def contacts_page() -> None:
    with ui.vstack(gap="lg"):
        ui.heading("Contacts", level=1, size="2xl")
        filter_bar()
        # The resizable group needs a height: in a vertical flow, its
        # panels have none to inherit.
        # An EXPLICIT height, not ``flex-1``: in a vertical flow,
        # ``flex-1`` grows with its content as long as the parent has no
        # height, and the list overflowed below the footer. Measured: the
        # pagination went outside the viewport.
        with ui.resizable(sizes=[34, 66], orientation="horizontal",
                          gap="md", name="contacts_split",
                          classes="h-[calc(100vh-14rem)]"):
            # ⚠️ BOTH panels are dressed the same, and it is finding
            # [28]. ``ui.resizable_panel`` has no padding — it renders no
            # class of its own, which is written and accepted — so the
            # left one stuck to the window's edge AND to the handle,
            # while the right one looked right BY ACCIDENT: its
            # ``ui.card`` brought its own.
            #
            # The answer is not a ``padding=`` on the panel: that would
            # be proprietary vocabulary for what standard Tailwind
            # already writes, and ``ui.card`` is the catalogue's only
            # component exposing that scale. It is the app that decides
            # how it breathes.
            #
            # The group's ``gap="md"``, for its part, is framework by
            # full right and does the other half: the cards touched the
            # handle (2 px between the two surfaces), because no
            # ancestor's padding can create space INSIDE the group. Only
            # the panels' parent knows where the handle is.
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
