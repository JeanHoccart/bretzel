"""App-wide error pages (a feature). Imports only ``bretzel``."""

from bretzel import error_page, ui


@error_page(404)
def not_found() -> None:
    with ui.vstack(gap="md", align="center", justify="center", classes="min-h-screen"):
        ui.heading("404", level=1, size="4xl", color="muted")
        ui.text("This page doesn't exist.", color="muted")
        ui.link("Back to the timer", href="/")


@error_page(500)
def server_error() -> None:
    with ui.vstack(gap="md", align="center", justify="center", classes="min-h-screen"):
        ui.heading("500", level=1, size="4xl", color="error")
        ui.text("Something went wrong on our side.", color="muted")
