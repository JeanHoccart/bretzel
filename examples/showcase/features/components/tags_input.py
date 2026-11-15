"""``/tags-input`` — values typed as tags, like the recipients of a mail."""

from bretzel import ui
from bretzel.state import ClientState, field
from examples.showcase.lib.example import example, page_header

SUMMARY = ("A field of free values, each one a tag: the recipients of a "
           "message, the labels of a task. Suggestions help while typing.")

PEOPLE = [
    ("maya.chen@lumen.example", "Maya Chen"),
    ("omar.haddad@lumen.example", "Omar Haddad"),
    ("lucia.romero@lumen.example", "Lucía Romero"),
    ("tom.becker@lumen.example", "Tom Becker"),
    ("aiko.tanaka@lumen.example", "Aiko Tanaka"),
    ("support@lumen.example", "Lumen support"),
]

EMAIL = r"[^@\s;,]+@[^@\s;,]+\.[^@\s;,]+"


def person(address, name):
    with ui.hstack(gap="sm", align="center") as row:
        ui.avatar(src=f"https://i.pravatar.cc/96?u={address}", name=name, size="xs")
        with ui.vstack(gap="none"):
            ui.text(name, size="sm")
            ui.text(address, size="xs", color="muted")
    return row


def recipients() -> None:
    # ``ghost``: no frame per field — the lines of the message do the work.
    with (ui.card(padding="none", classes="w-full max-w-xl"),
          ui.vstack(gap="none", classes="px-4")):
        for i, (label, value) in enumerate((("To", ["maya.chen@lumen.example"]), ("Cc", []))):
            if i:
                ui.divider(gap="none")
            with ui.hstack(gap="sm", align="center"):
                ui.text(label, color="muted", size="sm", classes="w-6 shrink-0")
                ui.tags_input(PEOPLE, value=value, render=person, pattern=EMAIL,
                              variant="ghost",
                              placeholder="Add people" if label == "To" else None)


def free_labels() -> None:
    with ui.form_field(label="Labels", hint="Enter, Tab or a comma adds one.",
                       classes="max-w-sm"):
        ui.tags_input(["design", "backend", "customer", "urgent"],
                      value=["design"], placeholder="Add a label")


def checked_values() -> None:
    with ui.form_field(label="Invite by e-mail", classes="max-w-md"):
        ui.tags_input(value=["omar.haddad@lumen.example", "not-an-address"],
                      pattern=EMAIL)


class Guests(ClientState):
    emails: list = field(default_factory=lambda: ["aiko.tanaka@lumen.example"])


def live_list() -> None:
    guests = Guests()
    with ui.vstack(gap="sm", classes="w-full max-w-md"):
        ui.tags_input(PEOPLE, value=guests.emails, render=person, pattern=EMAIL)
        with ui.hstack(gap="xs", align="baseline"):
            ui.text(guests.emails.length(), weight="semibold")
            ui.text("invited", color="muted", size="sm")


def page() -> None:
    page_header("tags_input", "Tags input", SUMMARY)
    example("Recipients of a message", recipients,
            note="Suggestions show on focus and narrow as you type; render= "
                 "draws each one. A tag shows the name, its tooltip the address. "
                 'variant="ghost": the lines of the message frame the fields.')
    example("Free labels", free_labels,
            note="Enter, Tab, « ; » and « , » turn what is typed into a tag; "
                 "pasting « a, b, c » makes three.")
    example("Values that must match", checked_values,
            note="pattern= says what a valid value is. A value that does not "
                 "match is kept, in red, the reason in its tooltip — the app "
                 "decides what to do with it.")
    example("A list the page reads", live_list, uses=[Guests],
            note="The value is a list in a ClientState: what is around the "
                 "field follows each tag added or removed.")
