"""``/banner`` — the strip that speaks to the whole page."""

from bretzel import ui
from examples.showcase.lib.example import example, page_header

SUMMARY = ("A full-width strip for news that concerns the whole page: "
           "six tones, three sizes, room for actions.")


def announcements() -> None:
    with ui.vstack(gap="sm", classes="w-full"):
        ui.banner("Scheduled maintenance on Sunday, 02:00–03:00 UTC.",
                  color="info")
        ui.banner("Your data export is ready to download.", color="success")
        ui.banner("You are viewing a read-only copy of this workspace.",
                  color="warning")
        ui.banner("Sync with Google Calendar has stopped.", color="error")
        ui.banner("Bretzel Conf 2026 — early-bird tickets end Friday.",
                  color="primary", icon="ticket")
        ui.banner("This workspace was archived on 12 March.", color="muted")


def with_actions() -> None:
    with ui.vstack(gap="sm", classes="w-full"):
        with ui.banner("Version 2.4 brings recurring invoices and a faster "
                       "dashboard.", title="Update available", color="info"):
            ui.button("Install now", size="sm")
            ui.button("Later", size="sm", variant="ghost")
        with ui.banner("Your trial ends in 3 days.", title="Keep your boards",
                       color="warning", icon="clock"):
            ui.button("Choose a plan", size="sm", color="warning")


def sizes() -> None:
    with ui.vstack(gap="sm", classes="w-full"):
        ui.banner("Small — for a dense admin screen.", color="info", size="sm")
        ui.banner("Medium — the default.", color="info", size="md")
        ui.banner("Large — for the one thing nobody should miss.",
                  color="info", size="lg")


def above_the_app() -> None:
    with ui.card(padding="none", classes="w-full"), ui.vstack(gap="none"):
        ui.banner("You are impersonating Ada Lovelace. Every action is "
                  "logged.", color="warning", icon="user-cog", size="sm")
        with ui.vstack(gap="md", classes="p-6"):
            with ui.hstack(gap="md", justify="between", wrap=True):
                with ui.vstack(gap="none"):
                    ui.heading("Invoices", level=3, size="lg")
                    ui.text("184 paid, 3 overdue", color="muted", size="sm")
                ui.button("New invoice", icon_left="plus")
            ui.progress(78, label="Paid this quarter · 78%", show_label=True)


def dismissible() -> None:
    ui.banner("We only use cookies that keep you signed in.",
              title="Privacy", color="muted", icon="cookie", dismissible=True)


def page() -> None:
    page_header("banner", "Banner", SUMMARY)
    example("Announcements", announcements, full=True,
            note="The four semantic tones pick their icon; primary and muted "
                 "take the one you give them.")
    example("With actions", with_actions, full=True,
            note="Whatever you put inside the banner lines up on its right.")
    example("Sizes", sizes, full=True)
    example("Above an application", above_the_app, full=True,
            note="Edge to edge at the top of a screen, where a status "
                 "belongs to everything below it.")
    example("Dismissible", dismissible, full=True,
            note="The × closes the banner in the browser. Give on_close a "
                 "Python function when the server must remember that this "
                 "user has already seen it.")
