"""``/attachments`` — the files joined to something, filled by any button."""

from bretzel import refreshable, ui
from bretzel.state import PageState, field
from examples.showcase.lib.example import example, page_header

SUMMARY = ("The list of files joined to a message or a record. Any button "
           "fills it with .pick(); it takes no room while empty, and shows the "
           "files the server already holds with the same look.")

RECEIVED = [
    {"name": "quote-2026-114.pdf", "size": 48213, "type": "application/pdf"},
    {"name": "site-plan.pdf", "size": 1_532_811, "type": "application/pdf"},
    {"name": "minutes.docx", "size": 20480,
     "type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"},
]


def send_reply(pieces=None) -> None:
    """``pieces`` is the list's ``name=``: the files arrive with the form."""
    files = pieces if isinstance(pieces, list) else [pieces] if pieces else []
    ui.notification(f"Reply sent with {len(files)} attachment(s).", color="success")


def reply() -> None:
    with ui.card(padding="md", classes="w-full max-w-xl"), \
            ui.form(on_submit=send_reply), ui.vstack(gap="sm"):
        ui.textarea(name="text", placeholder="Reply to Lumen Studio…", rows=3, size="sm")
        pieces = ui.attachments(name="pieces", multiple=True, max_size_mb=25,
                                paste=True, drop="form", size="sm")
        with ui.hstack(gap="xs", align="center"):
            ui.button("Send", type="submit", icon_left="send", size="sm")
            ui.icon_button("paperclip", variant="ghost", size="sm",
                           tooltip="Attach a file", aria_label="Attach a file",
                           on_click=pieces.pick())


def menu() -> None:
    with ui.vstack(gap="sm", classes="w-full max-w-xl"):
        pieces = ui.attachments(multiple=True, display="strip")
        with ui.dropdown(trigger=ui.button("Add", icon_left="plus", size="sm",
                                           variant="soft")):
            ui.dropdown_item("From this computer", icon_left="monitor",
                             on_click=pieces.pick())
            ui.dropdown_item("Clear the list", icon_left="x", on_click=pieces.clear())


class Received(PageState):
    files: list = field(default_factory=lambda: [dict(f) for f in RECEIVED])


def forget(key: str) -> None:
    received = Received()
    received.files = [f for f in received.files if f["name"] != key]


@refreshable
def received_mail() -> None:
    ui.attachments(files=Received().files, display="grid", on_remove=forget,
                   classes="w-full max-w-xl")


def page() -> None:
    page_header("attachments", "Attachments", SUMMARY)
    example("Attach to a reply", reply,
            uses=[send_reply],
            note="The list sits above the row, the paperclip beside Send: the row "
                 "never moves. Files can also be pasted in the text or dropped "
                 "anywhere on the form (drop=\"form\"); they leave with it.")
    example("From a menu", menu,
            note="pick() goes on any on_click, a menu entry included. "
                 "display=\"strip\" lines tiles up on one scrolling row.")
    example("A mail received", received_mail,
            uses=[Received, forget],
            note="files= shows what the server holds, with no form. on_remove= "
                 "puts a × on each and calls the handler with the file's key.")
