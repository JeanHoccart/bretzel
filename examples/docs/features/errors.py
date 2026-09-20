"""The docs' error pages — a feature like any other.

``@error_page`` is a free decorator; ``main`` picks these marks up
through ``app.include(errors)``.
"""

from bretzel import error_page, ui

from examples.docs.lib.i18n import tr


@error_page(404)
def not_found() -> None:
    with ui.vstack(gap="md", align="center", justify="center",
                   classes="min-h-screen"):
        ui.heading("404", level=1, size="4xl", color="muted")
        ui.text(tr("This page does not exist.", "Cette page n'existe pas."), color="muted")
        ui.link(tr("Back to the home page", "Retour à l'accueil"), href="/")


@error_page(500)
def server_error() -> None:
    with ui.vstack(gap="md", align="center", justify="center",
                   classes="min-h-screen"):
        ui.heading("500", level=1, size="4xl", color="error")
        ui.text(tr("Something broke on the server.", "Quelque chose a cassé côté serveur."), color="muted")
        ui.link(tr("Back to the home page", "Retour à l'accueil"), href="/")
