"""``/tooltip`` — a word of explanation, on hover or focus."""

from bretzel import ui
from bretzel.state import ClientState, field
from examples.showcase.lib.example import example, page_header

SUMMARY = ("Wrap anything to give it a hint on hover and keyboard focus — "
           "four sides, every colour, no request.")


def toolbar() -> None:
    with ui.card(padding="sm", classes="w-fit"), ui.hstack(gap="xs"):
        ui.icon_button("bold", variant="ghost", tooltip="Bold · Ctrl+B")
        ui.icon_button("italic", variant="ghost", tooltip="Italic · Ctrl+I")
        ui.icon_button("link", variant="ghost", tooltip="Insert a link")
        ui.icon_button("image", variant="ghost", tooltip="Add an image")
        ui.icon_button("list-checks", variant="ghost", tooltip="Checklist")


def sides() -> None:
    with ui.hstack(gap="md", wrap=True, justify="center"):
        with ui.tooltip("Opens above", position="top"):
            ui.button("Top", variant="outline")
        with ui.tooltip("Opens below", position="bottom"):
            ui.button("Bottom", variant="outline")
        with ui.tooltip("Opens on the left", position="left"):
            ui.button("Left", variant="outline")
        with ui.tooltip("Opens on the right", position="right"):
            ui.button("Right", variant="outline")


def colors() -> None:
    with ui.hstack(gap="md", wrap=True, justify="center"):
        with ui.tooltip("Everything is up to date", color="success"):
            ui.badge("Synced", color="success", variant="soft",
                     icon_left="check")
        with ui.tooltip("3 invoices are past their due date", color="error"):
            ui.badge("Overdue", color="error", variant="soft",
                     icon_left="circle-alert")
        with ui.tooltip("Renews on 1 October", color="primary"):
            ui.badge("Pro plan", color="primary", variant="soft",
                     icon_left="sparkles")
        with ui.tooltip("Available to admins only", color="muted"):
            ui.badge("Admin", color="muted", variant="soft", icon_left="lock")


def on_avatars() -> None:
    with ui.hstack(gap="sm", justify="center"):
        for name, role in (("Ada Lovelace", "Lead designer"),
                           ("Grace Hopper", "Engineering"),
                           ("Alan Turing", "Research"),
                           ("Katherine Johnson", "Data")):
            with ui.tooltip(f"{name} · {role}", delay=0):
                ui.avatar(src=f"https://i.pravatar.cc/96?u={name}", name=name)


class Hints(ClientState):
    shown: bool = field(default=True)


def toggle_hints() -> None:
    hints = Hints()
    with ui.vstack(gap="md", align="center"):
        with ui.hstack(gap="sm"):
            with ui.tooltip("Archive this conversation", disabled=~hints.shown):
                ui.button("Archive", icon_left="archive", variant="soft")
            with ui.tooltip("Snooze until tomorrow, 9:00", disabled=~hints.shown):
                ui.button("Snooze", icon_left="alarm-clock", variant="soft")
        ui.switch(checked=hints.shown, label="Show hints on hover")


def page() -> None:
    page_header("tooltip", "Tooltip", SUMMARY)
    example("On icon buttons", toolbar,
            note="An icon alone needs a word. tooltip= works on every "
                 "component, and on an icon button it also becomes its "
                 "accessible name.")
    example("Four sides", sides,
            note="with ui.tooltip(...) wraps what it explains; position= "
                 "picks the side.")
    example("Colours", colors,
            note="Tint the hint to match what it explains.")
    example("On a row of avatars", on_avatars,
            note="delay=0 shows it at once, for quick scanning.")
    example("Switched off by the user", toggle_hints, uses=[Hints],
            note="enabled is bindable: the switch writes a ClientState, and "
                 "the next hover obeys it — in the browser, without a "
                 "request.")
