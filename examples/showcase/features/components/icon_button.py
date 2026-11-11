"""``/icon-button`` — the button that is only an icon."""

from bretzel import ui
from bretzel.state import ClientState, field
from examples.showcase.lib.example import example, page_header

SUMMARY = ("A square button for toolbars and table rows: one icon, a tooltip "
           "that names it, and the same variants as a button.")


def variants() -> None:
    with ui.hstack(gap="sm", wrap=True, justify="center"):
        ui.icon_button("settings", variant="solid", tooltip="Solid",
                       aria_label="Settings")
        ui.icon_button("settings", variant="soft", tooltip="Soft",
                       aria_label="Settings")
        ui.icon_button("settings", variant="surface", tooltip="Surface",
                       aria_label="Settings")
        ui.icon_button("settings", variant="outline", tooltip="Outline",
                       aria_label="Settings")
        ui.icon_button("settings", variant="ghost", tooltip="Ghost",
                       aria_label="Settings")


def colors() -> None:
    with ui.hstack(gap="sm", wrap=True, justify="center"):
        ui.icon_button("sparkles", color="primary", variant="soft",
                       tooltip="Generate summary", aria_label="Generate summary")
        ui.icon_button("copy", color="secondary", variant="soft",
                       tooltip="Duplicate", aria_label="Duplicate")
        ui.icon_button("check", color="success", variant="soft",
                       tooltip="Approve", aria_label="Approve")
        ui.icon_button("flag", color="warning", variant="soft",
                       tooltip="Flag for review", aria_label="Flag for review")
        ui.icon_button("trash-2", color="error", variant="soft",
                       tooltip="Delete", aria_label="Delete")
        ui.icon_button("info", color="info", variant="soft",
                       tooltip="Details", aria_label="Details")


def sizes() -> None:
    with ui.hstack(gap="sm", wrap=True, justify="center"):
        for size in ("xs", "sm", "md", "lg", "xl"):
            ui.icon_button("bell", size=size, variant="outline",
                           tooltip=f"Size {size}", aria_label="Notifications")


def editor_toolbar() -> None:
    with ui.card(padding="sm", classes="w-fit"), ui.hstack(gap="xs"):
        ui.icon_button("bold", variant="ghost", size="sm", tooltip="Bold",
                       aria_label="Bold")
        ui.icon_button("italic", variant="ghost", size="sm", tooltip="Italic",
                       aria_label="Italic")
        ui.icon_button("underline", variant="ghost", size="sm",
                       tooltip="Underline", aria_label="Underline")
        ui.divider(orientation="vertical")
        ui.icon_button("list", variant="ghost", size="sm",
                       tooltip="Bulleted list", aria_label="Bulleted list")
        ui.icon_button("list-ordered", variant="ghost", size="sm",
                       tooltip="Numbered list", aria_label="Numbered list")
        ui.icon_button("link", variant="ghost", size="sm",
                       tooltip="Insert link", aria_label="Insert link")
        ui.divider(orientation="vertical")
        ui.icon_button("undo-2", variant="ghost", size="sm", tooltip="Undo",
                       aria_label="Undo")
        ui.icon_button("redo-2", variant="ghost", size="sm", tooltip="Redo",
                       aria_label="Redo", disabled=True)


TEAM = [
    {"name": "Maya Chen", "role": "Product designer"},
    {"name": "Omar Haddad", "role": "Backend engineer"},
    {"name": "Lucía Romero", "role": "Customer success"},
    {"name": "Tom Becker", "role": "Engineering manager"},
]


class Roster(ClientState):
    removed: list = field(default_factory=list)


def row_actions() -> None:
    removed = Roster().removed
    with ui.card(padding="sm", classes="w-full max-w-md"), ui.vstack(gap="xs"):
        for person in TEAM:
            name = person["name"]
            with ui.hstack(gap="sm", justify="between",
                           visible=~removed.contains(name)):
                with ui.hstack(gap="sm"):
                    ui.avatar(src=f"https://i.pravatar.cc/96?u={name}",
                              name=name, size="sm")
                    with ui.vstack(gap="none"):
                        ui.text(name, weight="medium")
                        ui.text(person["role"], size="sm", color="muted")
                ui.icon_button("user-minus", variant="ghost", color="error",
                               size="sm", tooltip=f"Remove {name}",
                               aria_label=f"Remove {name}",
                               on_click=removed.push(name))
        ui.text("Nobody left on the project.", color="muted",
                classes="self-center", visible=removed.length() == len(TEAM))
        ui.button("Restore team", icon_left="rotate-ccw", variant="ghost",
                  size="sm", on_click=removed.clear(), classes="self-end")


def states() -> None:
    with ui.hstack(gap="sm", wrap=True, justify="center"):
        ui.icon_button("refresh-cw", variant="outline", loading=True,
                       tooltip="Syncing…", aria_label="Sync")
        ui.icon_button("send", disabled=True, tooltip="Write a message first",
                       aria_label="Send")
        ui.icon_button("heart", variant="soft", color="error",
                       tooltip="Add to favourites", aria_label="Favourite")


def page() -> None:
    page_header("icon_button", "Icon button", SUMMARY)
    example("Variants", variants,
            note="The five button variants. Hover one: the tooltip says what "
                 "the icon means, and aria_label says it to screen readers.")
    example("Colours", colors,
            note="A semantic colour tells the action apart before the icon "
                 "is read.")
    example("Sizes", sizes)
    example("An editor toolbar", editor_toolbar,
            note="Ghost buttons stay quiet until hovered — the right weight "
                 "for a row of formatting tools.")
    example("Row actions", row_actions, uses=[Roster],
            note="Each row's button writes its name to a ClientState, and the "
                 "row hides itself in the browser. For a removal the server "
                 "must make, bind the name with functools.partial.")
    example("Loading and disabled", states)
