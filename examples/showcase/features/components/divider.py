"""``/divider`` — a quiet line between two things."""

from bretzel import ui
from examples.showcase.lib.example import example, page_header

SUMMARY = ("A horizontal or vertical rule, optionally with a label — to "
           "separate without adding another box.")


def setting_row(title: str, text: str, checked: bool) -> None:
    with ui.vstack(gap="none", tag="span") as label:
        ui.text(title, size="md", weight="medium")
        ui.text(text, size="sm", color="muted", weight="normal")
    ui.switch(checked=checked, name=title.lower().replace(" ", "_"), label=label,
              classes="w-full flex-row-reverse justify-between")


def sections() -> None:
    with ui.card(padding="md", classes="w-full max-w-md"), ui.vstack(gap="sm"):
        setting_row("Invoice paid", "When a customer settles an invoice.", True)
        ui.divider()
        setting_row("Weekly digest", "Every Monday at 9:00.", True)
        ui.divider()
        setting_row("Product news", "A few times a year, no more.", False)


def labelled() -> None:
    with ui.card(padding="lg", classes="w-full max-w-sm"), ui.vstack(gap="md"):
        ui.heading("Sign in to Northwind", level=3, size="lg")
        ui.button("Continue with Google", icon_left="chrome", variant="outline",
                  classes="w-full")
        ui.button("Continue with GitHub", icon_left="github", variant="outline",
                  classes="w-full")
        ui.divider(label="or with your email")
        with ui.form_field(label="Work email"):
            ui.input(type="email", placeholder="ada@northwind.io",
                     icon_left="mail")
        ui.button("Send me a link", classes="w-full")


def vertical() -> None:
    with ui.hstack(gap="sm", wrap=True, justify="center"):
        ui.text("Opened 2 days ago", size="sm", color="muted")
        ui.divider(orientation="vertical")
        ui.text("14 comments", size="sm", color="muted")
        ui.divider(orientation="vertical")
        ui.text("3 attachments", size="sm", color="muted")
        ui.divider(orientation="vertical")
        ui.badge("In review", color="warning", variant="soft", size="sm")


def colored() -> None:
    with ui.vstack(gap="sm", classes="w-full max-w-md"):
        ui.divider(label="Today", color="primary")
        ui.text("Payment of €1,150.00 received from Lumen Studio.", size="sm")
        ui.divider(label="Overdue", color="error")
        ui.text("INV-2039 for Atlas Freight is 12 days late.", size="sm")


def page() -> None:
    page_header("divider", "Divider", SUMMARY)
    example("Between settings", sections, uses=[setting_row],
            note="A card of rows reads as a list when each row is separated "
                 "by a line rather than boxed.")
    example("With a label", labelled,
            note="The label sits in a gap in the line — the classic "
                 "\"or\" between two ways of signing in.")
    example("Vertical, inside a row", vertical,
            note="orientation=\"vertical\" separates items of an hstack.")
    example("In colour", colored,
            note="color= tints the line and its label, to mark a section of "
                 "a timeline.")
