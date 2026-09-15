"""Pages d'erreur de la doc — une feature comme les autres.

``@error_page`` est un décorateur libre ; ``main`` ramasse ces marques via
``app.include(errors)``.
"""

from bretzel import error_page, ui


@error_page(404)
def not_found() -> None:
    with ui.vstack(gap="md", align="center", justify="center",
                   classes="min-h-screen"):
        ui.heading("404", level=1, size="4xl", color="muted")
        ui.text("Cette page n'existe pas.", color="muted")
        ui.link("Retour à l'accueil", href="/")


@error_page(500)
def server_error() -> None:
    with ui.vstack(gap="md", align="center", justify="center",
                   classes="min-h-screen"):
        ui.heading("500", level=1, size="4xl", color="error")
        ui.text("Quelque chose a cassé côté serveur.", color="muted")
        ui.link("Retour à l'accueil", href="/")
