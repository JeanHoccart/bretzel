"""features/errors — error : les pages 404 et 403, dans le shell.

Sans elles, un ``abort(404)`` rend une réponse nue : l'utilisateur perd la
navigation en même temps que la page. Les monter dans le shell garde le rail
sous la main.
"""

from __future__ import annotations

from bretzel import Feature, error_page, ui
from examples.crm.features.shell import shell


@error_page(404, layout=shell)
def not_found() -> None:
    with ui.vstack(gap="md"):
        ui.empty_state(
            "Page introuvable", icon="search-x",
            description="Ce contact, ce compte ou cette adresse n'existe pas.",
        )
        ui.link("Retour au pipeline", href="/", variant="underline",
                color="primary")


@error_page(403, layout=shell)
def forbidden() -> None:
    ui.empty_state(
        "Accès refusé", icon="lock",
        description="Cette vue n'est pas ouverte à ce profil.",
    )


feature = Feature(name="errors", kind="error",
                  provides=[not_found, forbidden])
