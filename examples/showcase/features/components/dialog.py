"""``/dialog`` — a modal that asks one question and waits for the answer."""

from bretzel import refreshable, ui
from bretzel.state import ClientState, PageState, field
from examples.showcase.lib.example import example, page_header

SUMMARY = ("A centred modal with backdrop, Escape and focus trap — opened "
           "with .open(), closed from any button inside it.")


def confirm_delete() -> None:
    dialog = ui.dialog(title="Delete “Website redesign”?", width="sm")
    with dialog, ui.vstack(gap="md"):
        ui.text("The 14 boards, 212 cards and every comment go with it. "
                "This cannot be undone.", color="muted")
        with ui.hstack(gap="sm", justify="end"):
            ui.button("Cancel", variant="ghost", on_click=dialog.close())
            ui.button("Delete project", color="error", icon_left="trash-2",
                      on_click=dialog.close())
    ui.button("Delete project", variant="outline", color="error",
              icon_left="trash-2", on_click=dialog.open())


API_KEYS = ["Production", "Staging", "CI pipeline"]


class ApiKeys(ClientState):
    revoked: list = field(default_factory=list)


def revoke_keys() -> None:
    keys = ApiKeys()
    with ui.vstack(gap="sm", classes="w-full max-w-md"):
        for name in API_KEYS:
            dialog = ui.dialog(title=f"Revoke the {name} key?", width="sm")
            with dialog, ui.vstack(gap="md"):
                ui.text("Apps using it will stop working at once.", color="muted")
                with ui.hstack(gap="sm", justify="end"):
                    ui.button("Keep it", variant="ghost", on_click=dialog.close())
                    ui.button("Revoke", color="error",
                              on_click=[keys.revoked.push(name), dialog.close()])
            with (ui.card(padding="sm", visible=~keys.revoked.contains(name)),
                  ui.hstack(justify="between")):
                with ui.hstack(gap="sm"):
                    ui.icon("key-round", color="primary")
                    ui.text(name, weight="medium")
                ui.button("Revoke", size="sm", variant="soft", color="error",
                          on_click=dialog.open())
        with ui.vstack(gap="sm", align="center",
                       visible=keys.revoked.length() == len(API_KEYS)):
            ui.text("No active keys.", color="muted")
            ui.button("Restore the demo keys", variant="outline",
                      icon_left="rotate-ccw", on_click=keys.revoked.clear())


class Invite(PageState):
    email: str = field(default="")
    role: str = field(default="editor")


class Team(PageState):
    members: list = field(default_factory=lambda: [["ada@northwind.io", "owner"]])


def send_invite(invite: Invite) -> None:
    email = str(invite.email).strip()
    if email:
        team = Team()
        team.members = [*team.members, [email, str(invite.role)]]
    invite.email = ""


@refreshable
def member_list() -> None:
    with ui.vstack(gap="sm", classes="w-full"):
        for email, role in list(Team().members):
            with ui.hstack(justify="between"):
                with ui.hstack(gap="sm"):
                    ui.avatar(name=email, size="sm", color="secondary")
                    ui.text(email)
                ui.badge(role.capitalize(), variant="soft", size="sm")


def invite_form() -> None:
    invite = Invite()
    dialog = ui.dialog(title="Invite a teammate", persistent=True)
    with dialog, ui.form(on_submit=[send_invite, dialog.close()]), ui.vstack(gap="md"):
        with ui.form_field(label="Email", required=True):
            ui.input(value=invite.email, type="email",
                     placeholder="grace@northwind.io", icon_left="mail")
        with ui.form_field(label="Role"):
            ui.select(value=invite.role, options=[("viewer", "Viewer"),
                                                  ("editor", "Editor"),
                                                  ("admin", "Admin")])
        with ui.hstack(gap="sm", justify="end"):
            ui.button("Cancel", variant="ghost", on_click=dialog.close())
            ui.button("Send invite", type="submit", icon_left="send")
    with ui.card(padding="md", classes="w-full max-w-md"), ui.vstack(gap="md"):
        with ui.hstack(justify="between"):
            ui.heading("Team", level=3, size="md")
            ui.button("Invite", size="sm", icon_left="user-plus", on_click=dialog.open())
        member_list()


def widths() -> None:
    with ui.hstack(gap="sm", wrap=True, justify="center"):
        for width, title in (("sm", "Rename the board"),
                             ("md", "Share this document"),
                             ("lg", "What's new in version 4.2"),
                             ("xl", "Compare the plans")):
            with ui.dialog(title=title, width=width) as dialog, ui.vstack(gap="md"):
                ui.text(f"This dialog uses width=\"{width}\". Pick the "
                        "narrowest one its content reads well in.",
                        color="muted")
                with ui.hstack(justify="end"):
                    ui.button("Got it", on_click=dialog.close())
            ui.button(f"Width {width}", variant="outline", on_click=dialog.open())


def session_expiry() -> None:
    with ui.dialog(title="Your session is about to expire", width="sm",
                   dismissible=False) as dialog, ui.vstack(gap="md"):
        ui.text("You have been inactive for 28 minutes. Unsaved changes "
                "to this invoice will be lost.", color="muted")
        with ui.hstack(gap="sm", justify="end"):
            ui.button("Sign out", variant="ghost", on_click=dialog.close())
            ui.button("Stay signed in", on_click=dialog.close())
    ui.button("Simulate inactivity", variant="outline", icon_left="timer",
              on_click=dialog.open())


def page() -> None:
    page_header("dialog", "Dialog", SUMMARY)
    example("Confirm a destructive action", confirm_delete,
            note="The dialog is declared once; the trigger calls "
                 "dialog.open() and every button inside can call "
                 "dialog.close(). No state to declare.")
    example("One confirmation per row", revoke_keys,
            uses=[ApiKeys],
            note="A list on on_click runs several actions in order: here it "
                 "marks the key revoked AND closes the dialog, all in the "
                 "browser.")
    example("A form in a dialog", invite_form,
            uses=[Invite, Team, send_invite, member_list],
            note="persistent=True keeps the close button but ignores Escape "
                 "and the backdrop, so a stray click never loses a half-typed "
                 "form. The handler receives the typed form state.")
    example("Widths", widths, note="sm, md (the default), lg and xl.")
    example("An answer is required", session_expiry,
            note="dismissible=False removes the close button, Escape and the "
                 "backdrop click: only the buttons inside can close it.")
