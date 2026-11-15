"""``/stack`` — vstack, hstack and flex: one axis at a time."""

from bretzel import ui
from examples.showcase.lib.example import example, page_header

SUMMARY = ("Rows and columns with a spacing scale — vstack and hstack for "
           "the everyday case, flex for the full axis API.")


def tile(label: str, icon: str) -> None:
    with ui.card(padding="sm"), ui.hstack(gap="sm"):
        ui.icon(icon, size="sm", color="primary")
        ui.text(label, size="sm", weight="medium")


def vertical() -> None:
    with ui.vstack(gap="sm", classes="w-full max-w-xs"):
        tile("Inbox", "inbox")
        tile("Drafts", "file-pen")
        tile("Scheduled", "clock")
        tile("Archive", "archive")


def horizontal() -> None:
    with (ui.card(padding="md", classes="w-full max-w-lg"),
          ui.hstack(gap="md", justify="between")):
        with ui.hstack(gap="sm"):
            ui.avatar(src="https://i.pravatar.cc/96?u=lena", name="Lena Park",
                      size="md")
            with ui.vstack(gap="none"):
                ui.text("Lena Park", weight="medium")
                ui.text("lena@northwind.io", size="sm", color="muted")
        ui.button("Message", icon_left="send", variant="outline", size="sm")


def justify_row(justify: str) -> None:
    with ui.vstack(gap="xs"):
        ui.text(f'justify="{justify}"', size="xs", color="muted",
                classes="font-mono")
        with ui.card(padding="xs"), ui.hstack(gap="sm", justify=justify):
            ui.button("Back", icon_left="arrow-left", variant="ghost", size="sm")
            ui.button("Save draft", variant="outline", size="sm")
            ui.button("Publish", icon_left="send", size="sm")


def justify() -> None:
    with ui.vstack(gap="md", classes="w-full"):
        for value in ("start", "center", "end", "between"):
            justify_row(value)


def wrapping() -> None:
    with ui.hstack(gap="sm", wrap=True, justify="center", classes="max-w-md"):
        for tag in ("Python", "FastAPI", "PostgreSQL", "Redis", "Tailwind",
                    "HTMX", "Docker", "Playwright", "Server-sent events"):
            ui.badge(tag, variant="soft", color="secondary")


def filter_bar() -> None:
    with ui.hstack(gap="md", wrap=True, grow="16rem", align="end",
                   classes="w-full"):
        with ui.form_field(label="Search"):
            ui.input(placeholder="Name, email or company", icon_left="search")
        with ui.form_field(label="Plan"):
            ui.select(options=["All plans", "Starter", "Team", "Scale"],
                      value="All plans")
        with ui.form_field(label="Country"):
            ui.select(options=["Anywhere", "France", "Germany", "Spain"],
                      value="Anywhere")


def responsive() -> None:
    with ui.flex(direction={"base": "col", "md": "row"}, gap="md",
                 classes="w-full"):
        with ui.card(padding="md", classes="md:w-56"), ui.vstack(gap="sm"):
            ui.text("Sidebar", weight="medium")
            ui.text("Stacks on top on a phone.", size="sm", color="muted")
        with ui.card(padding="md", classes="flex-1"), ui.vstack(gap="sm"):
            ui.text("Main content", weight="medium")
            ui.text("Takes the remaining width once the window is wide "
                    "enough for two columns.", size="sm", color="muted")


def page() -> None:
    page_header(("vstack", "hstack", "flex"), "Stack & flex", SUMMARY)
    example("A vertical list", vertical, uses=[tile],
            note="ui.vstack puts its children one under the other, with a "
                 "gap from the theme's spacing scale.")
    example("A horizontal row", horizontal,
            note="ui.hstack centres its children vertically by default — "
                 "the usual intent for a row.")
    example("Distribute along the row", justify, uses=[justify_row],
            full=True)
    example("Let it wrap", wrapping,
            note="wrap=True sends the overflow to the next line instead of "
                 "squeezing the tags.")
    example("A filter bar that shares the width", filter_bar, full=True,
            note="grow=\"16rem\" gives each field a 16rem basis, then shares "
                 "what is left; below that they wrap.")
    example("Change direction with the window", responsive, full=True,
            note="ui.flex takes a breakpoint dict: a column on a phone, a "
                 "row from md upwards.")
