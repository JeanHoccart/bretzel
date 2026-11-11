"""``/viewport`` — the frozen screen of a tool, and the regions that scroll.

A ``ui.viewport`` IS the browser window: it is ``fixed inset-0``. To show
one inside a preview box, each example pins it into a ``relative`` frame
# Fixed by design: `absolute!` holds it in this demo's box.
with ``classes="absolute!"`` — in an app you write ``ui.viewport()`` bare.
"""

from bretzel import ui
from examples.showcase.lib.example import example, page_header

SUMMARY = ("A screen that never scrolls as a whole: the navigation stays put, "
           "and each region scrolls on its own.")


def activity() -> list[tuple[str, str, str]]:
    return [
        ("Grace Hopper", "merged pull request #482", "2 min ago"),
        ("Alan Turing", "commented on Billing export", "9 min ago"),
        ("Ada Lovelace", "closed issue #1207", "24 min ago"),
        ("Katherine Johnson", "deployed v2.14 to production", "1 h ago"),
        ("Linus Pauling", "opened Faster invoice search", "2 h ago"),
        ("Hedy Lamarr", "invited 3 people to Nimbus", "3 h ago"),
        ("Grace Hopper", "renamed Q3 roadmap", "5 h ago"),
        ("Alan Turing", "archived Legacy importer", "Yesterday"),
        ("Ada Lovelace", "uploaded brand-kit.zip", "Yesterday"),
        ("Katherine Johnson", "resolved 12 alerts", "2 days ago"),
    ]


def app_shell() -> None:
    with (
        ui.vstack(gap="none", classes="relative h-[26rem] w-full overflow-hidden "
                                      "rounded-box border border-text/10"),
        # Fixed by design: `absolute!` holds it in this demo's box.
        ui.viewport(classes="absolute!"),
    ):
        with ui.sidebar(collapsible="none", width="sm", slots={"root": "h-full!"}):
            ui.sidebar_title("Nimbus", icon=ui.icon("cloud", color="primary", size="lg"))
            with ui.sidebar_section():
                ui.sidebar_item("Activity", icon="activity", active=True)
                ui.sidebar_item("Projects", icon="folder-kanban")
                ui.sidebar_item("Team", icon="users")
        with ui.pane(padding="lg", gap="sm"):
            ui.heading("Activity", level=3, size="xl")
            for who, what, when in activity():
                with ui.card(padding="sm"), ui.hstack(gap="sm"):
                    ui.avatar(name=who, size="sm", color="secondary")
                    with ui.vstack(gap="none", classes="min-w-0"):
                        ui.text(f"{who} {what}", size="sm", truncate=True)
                        ui.text(when, size="xs", color="muted")


def master_detail() -> None:
    with (
        ui.vstack(gap="none", classes="relative h-[24rem] w-full overflow-hidden "
                                      "rounded-box border border-text/10"),
        # Fixed by design: `absolute!` holds it in this demo's box.
        ui.viewport(classes="absolute!", grow="equal"),
    ):
        with ui.pane(padding="md", gap="sm"):
            ui.text("Conversations", weight="semibold")
            for who, what, _ in activity():
                with ui.card(padding="sm"), ui.vstack(gap="none"):
                    ui.text(who, weight="medium", size="sm")
                    ui.text(what, color="muted", size="sm", truncate=True)
        with ui.pane(padding="md", gap="md"):
            ui.text("Grace Hopper", weight="semibold")
            for _ in range(8):
                ui.text("The pull request is merged. Staging picks it up on "
                        "the next deploy; ping me if the export still times "
                        "out on the larger workspaces.", color="muted", size="sm")


def mobile_shell() -> None:
    with (
        ui.vstack(gap="none", classes="relative h-[32rem] w-full max-w-sm "
                                      "overflow-hidden rounded-box border border-text/10"),
        # Fixed by design: `absolute!` holds it in this demo's box.
        ui.viewport(direction="col", classes="absolute!"),
    ):
        with ui.navbar():
            with ui.navbar_section(side="left"):
                ui.heading("Activity", level=3, size="md")
            with ui.navbar_section(side="right"):
                ui.avatar(src="https://i.pravatar.cc/96?u=ada", name="Ada Lovelace",
                          size="sm")
        with ui.pane(padding="md", gap="sm"):
            for who, what, when in activity():
                with ui.card(padding="sm"), ui.vstack(gap="none"):
                    ui.text(f"{who} {what}", size="sm")
                    ui.text(when, size="xs", color="muted")
        with ui.bottom_bar():
            ui.bottom_bar_item("Activity", icon="activity", active=True)
            ui.bottom_bar_item("Projects", icon="folder-kanban")
            ui.bottom_bar_item("Team", icon="users")


def centred() -> None:
    with (
        ui.vstack(gap="none", classes="relative h-[24rem] w-full overflow-hidden "
                                      "rounded-box border border-text/10"),
        # Fixed by design: `absolute!` holds it in this demo's box.
        ui.viewport(classes="absolute!"),
        ui.pane(padding="lg", align="center", justify="center"),
        ui.card(padding="lg", classes="w-full max-w-sm"),
        ui.vstack(gap="md"),
    ):
        ui.heading("Sign in to Nimbus", level=3, size="lg")
        with ui.form_field(label="Work email"):
            ui.input(placeholder="ada@nimbus.io", type="email", icon_left="mail")
        ui.button("Send me a magic link", classes="w-full")


def page() -> None:
    page_header("viewport", "Viewport & pane", SUMMARY)
    example("An app shell", app_shell, uses=[activity], full=True,
            note="ui.viewport freezes the window; ui.pane is the region that "
                 "scrolls. Scroll the activity: the sidebar does not move. In "
                 "an app the viewport IS the window — here classes=\"absolute!\" "
                 "pins it inside the box.")
    example("Two regions, two scrollbars", master_detail, uses=[activity],
            full=True,
            note='A list and a conversation, each in its own pane. grow="equal" '
                 "shares the width between them.")
    example("A mobile shell", mobile_shell, uses=[activity],
            note='direction="col" stacks a top bar, the pane and a bottom bar: '
                 "both bars stay put while the feed scrolls between them.")
    example("Centred in the screen", centred, full=True,
            note='align="center" and justify="center" on the pane put a lone '
                 "card in the middle — a sign-in screen, an empty state.")
